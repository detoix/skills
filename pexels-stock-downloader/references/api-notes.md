# API Notes

Use the official Pexels API for video search and download.

Key points:

- Search endpoint: `https://api.pexels.com/videos/search`
- Send the API key directly in the `Authorization` header
- Do not prefix the key with `Bearer`
- Store the key in `PEXELS_API_KEY`

Useful search parameters:

- `query`
- `per_page`
- `page`
- `orientation`
- `min_duration`
- `max_duration`

Typical response fields used by the script:

- top-level `videos`
- per-video `id`, `duration`, `width`, `height`, `url`, `user`
- per-file `video_files[].link`, `video_files[].file_type`, `video_files[].quality`, `video_files[].width`, `video_files[].height`

Selection strategy:

- prefer downloadable MP4 files
- prefer HD over SD when available
- prefer the requested orientation when specified
- prefer larger resolution among otherwise similar matches

Keep the saved manifest because downstream assembly workflows can use it to trace search queries to downloaded files.
