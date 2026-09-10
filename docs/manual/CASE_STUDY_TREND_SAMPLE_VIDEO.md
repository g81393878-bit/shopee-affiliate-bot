# Trend sample video: local typography preview

Run `python tools/render_trend_sample.py` from the repository root on Windows. Requires edge-tts, Pillow with Thai shaping, PyThaiNLP, imageio-ffmpeg, and Windows Leelawadee fonts. Reads the reviewed iPhone script; writes only under artifacts/google_trends/iphone17_preview. No DB, uploader, notification or queue calls.

Output: iphone17_preview.mp4, caption.txt, scene cards, audio segments, timings.json, verification.log, and contact_sheet.jpg. Uses PremwadeeNeural +20%, volume 1.0, no atempo. Full HD portrait, five typography scenes. Spoken text exactly matches the reviewed script. Text wraps using PyThaiNLP newmm. No product photography or AI images used.

Incident: FFmpeg 4.2.2 concat could not resolve relative scene paths from an absolute Windows playlist path and reported Impossible to open scene_1.mp4. Fixed the subprocess working directory to the output directory. Re-running the complete renderer succeeded.

Validation: final video decoded completely; H.264 video and AAC audio present. Extracted a midpoint frame from each scene and visually checked the contact sheet for Thai text, clipping and scene content. Mean audio -18.8 dB, peak -4.1 dB, not silent. Hook audio approximately 2.11 seconds; first scene 2.26 seconds including padding. These are technical checks, not a claim of listening to every spoken word. No end-to-end social platform test or publishing performed.

This renderer is a sample workflow, not connected to the scheduled factory. Existing full-suite failures from the previous report session remain unresolved. No commit/push. External Google Docs synchronization not performed.

The renderer now also accepts a validated five-scene plan and output directory from `trend_autopilot.py`. A live smoke test used Apple iPhone 17 source data, passed the evidence-bound factual review after one automatic correction, rendered locally, and passed video QA. The smoke output was not moved to the posting queue.

## Motion and timed subtitles

Run `python tools/render_trend_sample.py --motion`. Output is separate: `artifacts/google_trends/iphone17_motion/iphone17_motion.mp4`. Uses continuous PremwadeeNeural +20% speech and 71 actual Edge WordBoundary events; 10 grouped subtitle cues with current-word highlights; 2.5% gentle zoom; 0.25-second visual cross-dissolves. Audio speed is unchanged, no atempo or audio overlaps. Generated captions.srt can be reused for editing. Cached voice.mp3 and words.json must be removed together when changing the speech; mismatched word text causes a validation error.

Visual QA initially found subtitle groups spanning scene boundaries. Grouping now breaks at scene phrases and question marks, in addition to its length limit. Re-rendered successfully. Validation confirmed all 10 cues have valid times within the clip and do not cross scene boundaries. Full decode: 1080x1920 at 30 fps, H.264 + AAC, duration 14.95 seconds. Audio mean -18.1 dB, peak -4.4 dB; no black interval >=0.3 seconds detected. Five scene screenshots inspected: Thai subtitles fit and highlights are visible. The shorter duration comes from a continuous TTS request rather than separately synthesized segments, not waveform acceleration. Local Python syntax check passed. This does not resolve the earlier unrelated full-suite failures; no publishing or commit performed.
