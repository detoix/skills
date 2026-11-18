#!/usr/bin/env python3
"""Write a VoxCPM2 acoustic GGUF with Q8_0 LocDiT transformer projections."""

import argparse
import os
from pathlib import Path
import tempfile

from gguf import GGMLQuantizationType, GGUFEndian, GGUFReader, GGUFWriter, quantize


PROJECTIONS = ('attn_q', 'attn_k', 'attn_v', 'attn_output', 'ffn_gate', 'ffn_up', 'ffn_down')
Q8 = GGMLQuantizationType.Q8_0


def write_variant(source: Path, destination: Path) -> int:
    if destination.exists():
        raise FileExistsError(destination)
    reader = GGUFReader(source)
    fields = reader.fields
    architecture = fields['general.architecture'].contents()
    if (architecture != 'voxcpm-acoustic' or fields['voxcpm.model_version'].contents() != 2.0 or
            reader.endianess != GGUFEndian.LITTLE):
        raise ValueError('Expected a little-endian VoxCPM2 acoustic GGUF')
    layers = fields['voxcpm.locdit.n_layer'].contents()
    expected = {f'locdit.blk.{i}.{projection}.weight' for i in range(layers) for projection in PROJECTIONS}
    selected = {tensor.name for tensor in reader.tensors if tensor.name in expected and
                tensor.tensor_type == GGMLQuantizationType.F16 and tensor.data.ndim == 2}
    if not expected or selected != expected:
        raise ValueError('Expected F16 matrices for every LocDiT transformer projection')

    with tempfile.TemporaryDirectory(prefix='.locdit-', dir=destination.parent) as staging:
        path = Path(staging) / 'acoustic.gguf'
        writer = GGUFWriter(path, architecture)
        if 'general.alignment' in fields:
            writer.add_custom_alignment(reader.alignment)
        for name, field in fields.items():
            if not name.startswith('GGUF.') and name not in ('general.architecture', 'general.alignment'):
                writer.add_key_value(name, field.contents(), *field.types)
        for tensor in reader.tensors:
            if tensor.name in selected:
                writer.add_tensor(tensor.name, quantize(tensor.data, Q8), raw_dtype=Q8)
            else:
                writer.add_tensor(tensor.name, tensor.data, raw_dtype=tensor.tensor_type,
                                  tensor_endianess=reader.endianess)
        writer.write_header_to_file()
        try:
            writer.write_kv_data_to_file()
            writer.write_tensors_to_file()
        finally:
            writer.close()
        os.link(path, destination)
    return len(selected)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path, help='VoxCPM2 acoustic F16 GGUF')
    parser.add_argument('destination', type=Path, help='new acoustic GGUF path')
    args = parser.parse_args()
    count = write_variant(args.source, args.destination)
    print(f'Wrote {args.destination} with {count} Q8_0 LocDiT matrices')


if __name__ == '__main__':
    main()
