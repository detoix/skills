"""Faster VoxCPM2 generation on CPU: same model and sampler as upstream ``_generate_with_prompt_cache``.

What changes is how the work runs:
- float32 throughout: CPUs without native bfloat16 run the diffusion head and prefill faster in float32;
- the diffusion head is compiled with frozen, prepacked weights (eager matmuls are slow at its small batch sizes);
- a decode step attends to the filled part of the KV cache only (upstream masks all 8192 slots every step);
- several lines decode together and share each LM weight read; a finished line's row takes the next queued line;
- each line draws its diffusion noise from its own seeded generator, so it renders the same alone or in a batch.
"""

from __future__ import annotations

import re
import sys
from collections import deque
from dataclasses import dataclass, field


def _hide_mismatched_triton():
    """Inductor imports ``triton_key`` from any installed triton; the runtime's (pulled in by whisperx) is built for a
    newer torch and fails that import. CPU kernels don't use triton, so hide it from this process."""
    try:
        from triton.compiler.compiler import triton_key  # noqa: F401
    except ImportError:
        for name in [m for m in sys.modules if m == "triton" or m.startswith("triton.")]:
            del sys.modules[name]
        sys.modules["triton"] = None


_hide_mismatched_triton()

import torch  # noqa: E402
import torch.nn.functional as F  # noqa: E402
from voxcpm.modules.minicpm4 import model as minicpm  # noqa: E402

STREAMING_PREFIX_LEN = 4  # upstream default: trailing prompt patches decoded with continuation output


def _attention_step(self, hidden_states, position_emb, position_id, kv_cache):
    """MiniCPMAttention.forward_step for rows at their own positions, attending to filled slots only."""
    bsz = hidden_states.size(0)
    q = self.q_proj(hidden_states).view(bsz, 1, self.num_heads, self.head_dim).transpose(1, 2)
    k = self.k_proj(hidden_states).view(bsz, 1, self.num_key_value_heads, self.head_dim).transpose(1, 2)
    v = self.v_proj(hidden_states).view(bsz, 1, self.num_key_value_heads, self.head_dim).transpose(1, 2)
    if position_emb is not None:
        cos, sin = position_emb
        q, k = minicpm.apply_rotary_pos_emb(q, k, cos.view(bsz, 1, 1, -1), sin.view(bsz, 1, 1, -1))

    key_cache, value_cache = kv_cache
    rows = torch.arange(bsz)
    key_cache[rows, :, position_id] = k[:, :, 0]
    value_cache[rows, :, position_id] = v[:, :, 0]

    length = int(position_id.max()) + 1
    mask = None
    if bsz > 1:
        mask = (torch.arange(length) <= position_id.view(bsz, 1)).view(bsz, 1, 1, length)
    out = F.scaled_dot_product_attention(
        q, key_cache[:, :, :length], value_cache[:, :, :length], attn_mask=mask, enable_gqa=True
    )
    return self.o_proj(out.transpose(1, 2).reshape(bsz, self.num_heads * self.head_dim))


class RowKVCache:
    """StaticKVCache with one row per line in flight; layers see the first ``active`` rows."""

    def __init__(self, num_layers, num_kv_heads, head_dim, rows, length):
        self.kv_cache = torch.zeros(2, num_layers, rows, num_kv_heads, length, head_dim)
        self.active = 0

    def get_layer_cache(self, layer_idx):
        return self.kv_cache[0, layer_idx, : self.active], self.kv_cache[1, layer_idx, : self.active]

    def load(self, row, layer_kvs):
        n = layer_kvs[0][0].size(2)
        for i, (k, v) in enumerate(layer_kvs):
            self.kv_cache[0, i, row, :, :n] = k[0]
            self.kv_cache[1, i, row, :, :n] = v[0]

    def move(self, src, dst):
        self.kv_cache[:, :, dst] = self.kv_cache[:, :, src]


class CompiledOrEager(torch.nn.Module):
    """Static-shape inductor compile with frozen weights; eager if compiling fails.

    The batch is padded to a power of two with copies of its last row: odd sizes can run slower than the next power
    of two, and fewer sizes mean fewer compiles.
    """

    def __init__(self, module):
        super().__init__()
        import torch._dynamo
        import torch._inductor.config

        torch._inductor.config.freezing = True
        torch._dynamo.config.automatic_dynamic_shapes = False  # a dynamic batch dim compiles much slower kernels
        torch._dynamo.config.recompile_limit = 64
        self.module = module
        self.compiled = torch.compile(module, dynamic=False)

    def forward(self, *args):
        if self.compiled is not None:
            n = args[0].size(0)
            size = 1 << (n - 1).bit_length()
            padded = [torch.cat((a, a[-1:].expand(size - n, *a.shape[1:]))) for a in args] if size != n else args
            try:
                return self.compiled(*padded)[:n]
            except Exception as exc:  # no C++ compiler, unsupported op, ...
                print(f"torch.compile failed, continuing eager: {type(exc).__name__}: {exc}", file=sys.stderr)
                self.compiled = None
        return self.module(*args)


def prepare(model, compile=True):
    """Switch a loaded CPU VoxCPM2Model to float32 and batched decoding; optionally compile the diffusion head."""
    model.to(torch.float32)
    model.config.dtype = "float32"
    model.base_lm.kv_cache = model.residual_lm.kv_cache = None  # each run allocates RowKVCache rows
    minicpm.MiniCPMAttention.forward_step = _attention_step
    if compile:
        model.feat_decoder.estimator = CompiledOrEager(model.feat_decoder.estimator)
    return model


class _Captured(Exception):
    pass


def build_inputs(model, text, prompt_cache, max_len, ratio_threshold):
    """Upstream's own input layout for one line, captured where its decode loop would start."""
    seen = {}

    def capture(text_token, text_mask, feat, feat_mask, **kwargs):
        seen.update(text=text_token, text_mask=text_mask, feat=feat, feat_mask=feat_mask, max_len=kwargs["max_len"])
        raise _Captured

    model._inference = capture
    try:
        next(
            model._generate_with_prompt_cache(
                target_text=text,
                prompt_cache=prompt_cache,
                max_len=max_len,
                retry_badcase=False,
                retry_badcase_ratio_threshold=ratio_threshold,
            )
        )
    except _Captured:
        pass
    finally:
        del model._inference
    return seen


@dataclass
class Job:
    index: int
    text: str
    inputs: dict
    target_len: int
    generator: torch.Generator
    attempt: int = 0


@dataclass
class Row:
    job: Job
    position: int
    context: list = field(default_factory=list)
    patches: list = field(default_factory=list)


def generate_many(
    model,
    texts,
    prompt_cache,
    seed,
    rows=4,
    inference_timesteps=20,
    cfg_value=2.0,
    min_len=2,
    max_len=4096,
    retry_badcase_max_times=3,
    retry_badcase_ratio_threshold=6.0,
):
    """Yield ``(index, waveform, info)`` as lines finish; line ``i`` (0-based) uses noise seed ``seed + i``."""
    jobs = deque()
    for index, text in enumerate(texts):
        text = re.sub(r"\s+", " ", text.replace("\n", " "))
        jobs.append(
            Job(
                index=index,
                text=text,
                inputs=build_inputs(model, text, prompt_cache, max_len, retry_badcase_ratio_threshold),
                target_len=len(model.text_tokenizer(text)),
                generator=torch.Generator().manual_seed(seed + index),
            )
        )

    capacity = max(job.inputs["text"].size(1) + job.inputs["max_len"] for job in jobs) + 1
    rows = max(1, min(rows, len(jobs)))
    lm_cfg = model.config.lm_config
    head_dim = lm_cfg.kv_channels or lm_cfg.hidden_size // lm_cfg.num_attention_heads
    base_cache = RowKVCache(lm_cfg.num_hidden_layers, lm_cfg.num_key_value_heads, head_dim, rows, capacity)
    residual_cache = RowKVCache(model.config.residual_lm_num_layers, lm_cfg.num_key_value_heads, head_dim, rows, capacity)
    model.base_lm.kv_cache = base_cache
    model.residual_lm.kv_cache = residual_cache

    scale_emb = lm_cfg.scale_emb if lm_cfg.use_mup else 1.0
    active: list[Row] = []
    lm_hidden = residual_hidden = cond = None  # state of the active rows, in row order

    def encode_patches(feat):
        return model.enc_to_lm_proj(model.feat_encoder(feat))

    def start(job, row_index):
        """Prefill one line into a cache row (batch of one: lines differ in length)."""
        text, text_mask, feat, feat_mask = (job.inputs[k] for k in ("text", "text_mask", "feat", "feat_mask"))
        feat_embed = encode_patches(feat)
        text_embed = model.base_lm.embed_tokens(text) * scale_emb
        combined = text_mask.unsqueeze(-1) * text_embed + feat_mask.unsqueeze(-1) * feat_embed
        enc_outputs, base_kv = model.base_lm(inputs_embeds=combined, is_causal=True)
        enc_outputs = model.fsq_layer(enc_outputs) * feat_mask.unsqueeze(-1) + enc_outputs * text_mask.unsqueeze(-1)
        residual_inputs = model.fusion_concat_proj(torch.cat((enc_outputs, feat_mask.unsqueeze(-1) * feat_embed), -1))
        residual_outputs, residual_kv = model.residual_lm(inputs_embeds=residual_inputs, is_causal=True)
        base_cache.load(row_index, base_kv)
        residual_cache.load(row_index, residual_kv)

        row = Row(job=job, position=text.size(1))
        if feat_mask[0, -1].item() == 1:
            audio_indices = feat_mask.squeeze(0).nonzero(as_tuple=True)[0]
            context_len = min(STREAMING_PREFIX_LEN - 1, len(audio_indices))
            row.context = list(feat[:, audio_indices[-context_len:]].split(1, dim=1))
        return row, enc_outputs[:, -1], residual_outputs[:, -1], feat[:, -1].clone()

    def finish(row):
        """Decode a finished row, or requeue it as a bad case (upstream keeps the last attempt)."""
        job = row.job
        if len(row.patches) >= job.target_len * retry_badcase_ratio_threshold:
            job.attempt += 1
            print(f"  line {job.index + 1}: bad case, audio/text ratio {len(row.patches) / job.target_len:.1f}")
            if job.attempt < retry_badcase_max_times:
                jobs.appendleft(job)
                return None
        seq = torch.cat(row.context + row.patches, dim=1)  # [1, t, p, d]
        latent = seq.permute(0, 3, 1, 2).reshape(1, seq.size(-1), -1)
        audio = model.audio_vae.decode(latent)
        skip = model.patch_size * model._decode_chunk_size * len(row.context)
        return audio[..., skip:].squeeze(1).squeeze(0)

    def fill(row_index, row, hidden, residual, prefix):
        nonlocal lm_hidden, residual_hidden, cond
        if row_index == len(active):
            active.append(row)
            lm_hidden = hidden if lm_hidden is None else torch.cat((lm_hidden, hidden))
            residual_hidden = residual if residual_hidden is None else torch.cat((residual_hidden, residual))
            cond = prefix if cond is None else torch.cat((cond, prefix))
        else:
            active[row_index] = row
            lm_hidden[row_index], residual_hidden[row_index], cond[row_index] = hidden[0], residual[0], prefix[0]

    while jobs and len(active) < rows:
        fill(len(active), *start(jobs.popleft(), len(active)))

    t_span = torch.linspace(1, 0, inference_timesteps + 1)
    t_span = t_span + (torch.cos(torch.pi / 2 * t_span) - 1 + t_span)  # upstream sway_sampling_coef=1.0

    while active:
        n = len(active)
        base_cache.active = residual_cache.active = n
        mu = torch.cat((model.lm_to_dit_proj(lm_hidden), model.res_to_dit_proj(residual_hidden)), dim=-1)
        z = torch.cat([torch.randn((1, model.feat_dim, model.patch_size), generator=r.job.generator) for r in active])
        pred = model.feat_decoder.solve_euler(
            z, t_span, mu, cond.transpose(1, 2).contiguous(), cfg_value=cfg_value, use_cfg_zero_star=True
        ).transpose(1, 2)  # [n, p, d]
        embed = encode_patches(pred.unsqueeze(1))[:, 0]
        stop = model.stop_head(model.stop_actn(model.stop_proj(lm_hidden))).argmax(dim=-1).tolist()

        done = []
        for r, row in enumerate(active):
            row.patches.append(pred[r : r + 1].unsqueeze(1))
            step = len(row.patches) - 1
            if (step > min_len and stop[r] == 1) or step + 1 >= row.job.inputs["max_len"]:
                done.append(r)

        positions = torch.tensor([row.position for row in active])
        lm_hidden = model.fsq_layer(model.base_lm.forward_step(embed, positions).clone())
        residual_inputs = model.fusion_concat_proj(torch.cat((lm_hidden, embed), dim=-1))
        residual_hidden = model.residual_lm.forward_step(residual_inputs, positions).clone()
        cond = pred.clone()
        for row in active:
            row.position += 1

        for r in reversed(done):  # descending, so a row moved down from the end is never one still to handle
            row = active[r]
            audio = finish(row)
            if audio is not None:
                yield row.job.index, audio, {"steps": len(row.patches), "attempts": row.job.attempt + 1}
            if jobs:
                fill(r, *start(jobs.popleft(), r))
                continue
            last = len(active) - 1
            if r != last:
                base_cache.move(last, r)
                residual_cache.move(last, r)
                active[r] = active[last]
                lm_hidden[r], residual_hidden[r], cond[r] = lm_hidden[last], residual_hidden[last], cond[last]
            active.pop()
            lm_hidden, residual_hidden, cond = lm_hidden[:last], residual_hidden[:last], cond[:last]
