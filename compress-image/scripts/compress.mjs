import { link, mkdir, mkdtemp, readFile, rename, rm, stat, writeFile } from 'node:fs/promises';
import { basename, dirname, extname, join, parse, resolve } from 'node:path';
import { parseArgs } from 'node:util';
import { loadSharp } from './runtime.mjs';

const encoders = {
  png: (image) => image.png({ compressionLevel: 9, adaptiveFiltering: true }),
  jpeg: (image) => image.jpeg({ quality: 80, mozjpeg: true }),
  webp: (image, lossless) => image.webp(lossless
    ? { lossless: true, exact: true, effort: 6 }
    : { quality: 70, preset: 'photo', effort: 6, smartSubsample: true, alphaQuality: 100 }),
  avif: (image) => image.avif({ quality: 50, effort: 4 }),
};
const resizeModes = { scale: 'inside', fit: 'inside', cover: 'cover', thumb: 'cover' };
const maxDownloadBytes = 64 * 1024 * 1024;

const usage = `Usage: node compress.mjs <file-or-http-url> [options]
  -o, --output <path>      Output file or existing directory
  -f, --format <format>    keep|png|jpeg|webp|avif|smallest (default: keep)
      --resize <method>    scale|fit|cover|thumb
      --width <pixels>     Target width
      --height <pixels>    Target height
      --lossless           Encode PNG or WebP without discarding pixel data
      --keep-metadata      Retain metadata supported by the output format
      --force              Replace an existing output file
      --json               Write output details as JSON
      --validate           Check the local installation
  -h, --help              Show this help
`;

function getOptions() {
  const { values, positionals } = parseArgs({
    allowPositionals: true,
    options: {
      help: { type: 'boolean', short: 'h' },
      validate: { type: 'boolean' },
      output: { type: 'string', short: 'o' },
      format: { type: 'string', short: 'f', default: 'keep' },
      resize: { type: 'string' },
      width: { type: 'string' },
      height: { type: 'string' },
      lossless: { type: 'boolean' },
      'keep-metadata': { type: 'boolean' },
      force: { type: 'boolean' },
      json: { type: 'boolean' },
    },
  });
  if (values.help) return values;
  if (values.validate ? positionals.length : positionals.length !== 1) {
    throw new Error('Provide one image file or HTTP URL, or use --validate.');
  }
  const format = values.format.toLowerCase();
  if (!['keep', 'smallest'].includes(format) && !Object.hasOwn(encoders, format)) {
    throw new Error(`Unsupported output format: ${format}`);
  }
  const dimensions = ['width', 'height'].filter(axis => values[axis] !== undefined);
  const resize = values.resize?.toLowerCase();
  if (resize && !Object.hasOwn(resizeModes, resize)) throw new Error(`Unsupported resize method: ${resize}`);
  const expectedDimensions = resize === 'scale' ? 1 : resize ? 2 : 0;
  if (dimensions.length !== expectedDimensions) {
    throw new Error('Scale requires one dimension. Fit, cover and thumb require both. Dimensions require --resize.');
  }
  for (const axis of dimensions) {
    const size = Number(values[axis]);
    if (!/^[0-9]+$/.test(values[axis]) || !Number.isSafeInteger(size) || size < 1) {
      throw new Error(`--${axis} must be a positive integer.`);
    }
    values[axis] = size;
  }
  if (values.width * values.height > 100_000_000) throw new Error('Resize exceeds 100 megapixels.');
  return { ...values, input: positionals[0], format, resize };
}

async function readInput(input) {
  if (!/^https?:\/\//i.test(input)) {
    const path = resolve(input);
    return { data: await readFile(path), folder: dirname(path), stem: parse(path).name };
  }

  const url = new URL(input);
  const response = await fetch(url, { signal: AbortSignal.timeout(30_000) });
  if (!response.ok || !response.body) throw new Error(`Image download failed (HTTP ${response.status}).`);
  const chunks = [];
  let length = 0;
  for await (const chunk of response.body) {
    length += chunk.length;
    if (length > maxDownloadBytes) throw new Error('Image download exceeds 64 MiB.');
    chunks.push(chunk);
  }
  return { data: Buffer.concat(chunks, length), folder: process.cwd(), stem: parse(basename(url.pathname)).name || 'image' };
}

function isAnimatedPng(data) {
  for (let offset = 8; offset + 12 <= data.length;) {
    const type = data.toString('ascii', offset + 4, offset + 8);
    if (type === 'acTL') return true;
    if (type === 'IDAT' || type === 'IEND') return false;
    offset += 12 + data.readUInt32BE(offset);
  }
  return false;
}

async function compress(sharp, data, options) {
  const image = sharp(data, { limitInputPixels: 100_000_000 });
  const info = await image.metadata();
  const sourceFormat = info.format === 'heif' && info.compression === 'av1' ? 'avif' : info.format;
  if (!Object.hasOwn(encoders, sourceFormat)) throw new Error('Expected a PNG, JPEG, WebP or AVIF image.');
  if (info.pages > 1 || (sourceFormat === 'png' && isAnimatedPng(data))) {
    throw new Error('Animated images require an animation-aware optimizer.');
  }
  const normalizedOrientation = !info.orientation || info.orientation === 1;
  if (!options.lossless) image.autoOrient();
  if (options['keep-metadata'] || (options.lossless && !normalizedOrientation)) image.keepMetadata();
  if (options.resize) {
    const dimensions = options.lossless ? info : info.autoOrient;
    const width = options.width ?? Math.round(dimensions.width * options.height / dimensions.height);
    const height = options.height ?? Math.round(dimensions.height * options.width / dimensions.width);
    if (width * height > 100_000_000) throw new Error('Resize exceeds 100 megapixels.');
    image.resize(options.width, options.height, {
      fit: resizeModes[options.resize],
      position: options.resize === 'thumb' ? 'attention' : 'centre',
      withoutEnlargement: resizeModes[options.resize] === 'inside',
    });
  }

  let targets = options.format === 'smallest'
    ? Object.keys(encoders)
    : [options.format === 'keep' ? sourceFormat : options.format];
  if (options.format === 'smallest' && info.hasAlpha) targets = targets.filter(format => format !== 'jpeg');
  if (options.lossless && options.format === 'smallest') targets = targets.filter(format => format === 'png' || format === 'webp');
  if (info.hasAlpha && targets.includes('jpeg')) throw new Error('Choose PNG, WebP or AVIF to keep transparency.');
  if (options.lossless && targets.some(format => format !== 'png' && format !== 'webp')) {
    throw new Error('The lossless mode supports PNG and WebP output.');
  }
  if (info.depth !== 'uchar') {
    if (options.format === 'smallest') targets = ['png'];
    if (targets[0] !== 'png') throw new Error('Choose PNG to retain source precision above 8 bits.');
    image.pipelineColourspace('rgb16').toColourspace('rgb16');
  }
  if (options.lossless && info.hasProfile) image.keepIccProfile();

  let best;
  for (const format of targets) {
    let candidate = await encoders[format](image.clone(), options.lossless).toBuffer();
    if (format === 'png' && !options.lossless && !info.hasAlpha && info.depth === 'uchar') {
      const indexed = await image.clone().png({
        palette: true, colours: 256, dither: 0.3, compressionLevel: 9,
      }).toBuffer();
      if (indexed.length < candidate.length) candidate = indexed;
    }
    const canReuse = (normalizedOrientation || options.lossless) && !options.resize && sourceFormat === format;
    if (canReuse && data.length <= candidate.length) candidate = data;
    if (!best || candidate.length < best.data.length) best = { data: candidate, format };
  }
  const decoded = await sharp(best.data).metadata();
  return { ...best, width: decoded.autoOrient.width, height: decoded.autoOrient.height };
}

async function saveOutput(source, result, options) {
  const extension = result.format === 'jpeg' ? 'jpg' : result.format;
  const name = `${source.stem}.optimized.${extension}`;
  let output = join(source.folder, name);
  if (options.output) {
    output = resolve(options.output);
    const info = await stat(output).catch(error => {
      if (error.code !== 'ENOENT') throw error;
      return null;
    });
    if (info?.isDirectory()) output = join(output, name);
    const suffix = extname(output).slice(1).toLowerCase();
    if (suffix && suffix !== extension && suffix !== result.format) {
      throw new Error(`Output extension .${suffix} does not match ${result.format}.`);
    }
  }

  const parent = dirname(output);
  await mkdir(parent, { recursive: true });
  const staging = await mkdtemp(join(parent, '.compress-image-'));
  const file = join(staging, 'output');
  try {
    await writeFile(file, result.data);
    if (options.force) await rename(file, output);
    else await link(file, output);
  } catch (error) {
    if (error.code === 'EEXIST') throw new Error(`Output already exists: ${output}. Use --force to replace it.`);
    throw error;
  } finally {
    await rm(staging, { recursive: true, force: true });
  }
  return output;
}

async function main() {
  const options = getOptions();
  if (options.help) {
    process.stdout.write(usage);
    return;
  }

  if (options.validate) {
    const sharp = await loadSharp();
    const report = { sharp: sharp.versions.sharp, libvips: sharp.versions.vips };
    console.log(options.json ? JSON.stringify(report) : `Local Sharp ${report.sharp} is ready.`);
    return;
  }

  const source = await readInput(options.input);
  const result = await compress(await loadSharp(), source.data, options);
  const output = await saveOutput(source, result, options);
  const inputBytes = source.data.length;
  const outputBytes = result.data.length;
  const report = {
    output, format: result.format, width: result.width, height: result.height, inputBytes, outputBytes,
    savedBytes: inputBytes - outputBytes,
    reductionPercent: Number(((1 - outputBytes / inputBytes) * 100).toFixed(2)),
  };
  console.log(options.json ? JSON.stringify(report) : `${output}\n${inputBytes} → ${outputBytes} bytes`);
}

main().catch(error => {
  console.error(error.message);
  process.exitCode = 1;
});
