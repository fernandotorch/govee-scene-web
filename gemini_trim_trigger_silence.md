# Task: Trim the trailing silence of trigger sounds at pack export

Many trigger SFX files have a long stretch of silence after the actual sound. The app ducks the ambient bed and Spotify for the full file length, so that silence now keeps the music low for seconds after the sound has ended. Fix it at export, in `_do_export` in `govee_controller.py`.

## Rules
- Trim only audio ids that are used as a **trigger sound** (`scenes[].triggers[].sound`). Never trim ambient beds (`scenes[].ambient`), because trimming would break their loops.
  - If an id is used both as a trigger and as an ambient, do not trim it.
- Trim only **trailing** silence. Leading silence stays exactly as it is, because light flashes are timed from the start of the sound.
- Keep a short natural tail: 0.3 s of the silence stays.
- **Never modify the files in `SFX_DIR`.** Only the copy written into the ZIP is trimmed.
- ffmpeg filter for the trim (re-encode as libvorbis `-q:a 4`, like the rest of the export):
  `areverse,silenceremove=start_periods=1:start_threshold=-50dB:start_silence=0.3,areverse`
- Cache the trimmed output so re-exports are fast:
  - Directory: `os.path.join(UPLOADS_DIR, 'trim_cache')`.
  - Key: `sha1(abs source path + mtime + size)`.
  - Reuse the cached file when it exists.
- After trimming, measure the trimmed file with the existing `_get_duration`. Write that value as `duration_ms` into `zip_manifest[audio_id]`, the manifest that goes inside the ZIP. Do **not** change the `audio_manifest` saved back to the session JSON on disk.
- If ffmpeg fails, or the trimmed result is shorter than 50 ms (for example a whole file under the threshold), fall back to the untrimmed file, add a warning `Trim skipped: <file>`, and continue.
- This applies after the existing format handling. The source may already be `.ogg`, or it may be converted first by the existing path; in both cases, trim the file that would go into the ZIP.
- Log one line per trimmed file with the old and new duration, e.g. `Trimmed thunder.ogg: 9.8s -> 3.1s`.

## Constraints
- Change only what is needed in `_do_export`, plus small new helper functions.
- This repository has **uncommitted work in progress** in `govee_controller.py`, `templates/studio.html` and the session/pack files. Do not revert, reformat or touch any of it. Make a surgical edit.
- Do not commit. Do not restart the Studio server.

## Verify
- `python3 -m py_compile govee_controller.py`
- Write a quick standalone check script in `/tmp`:
  - generate a test OGG with ffmpeg: 1 s of a sine tone followed by 5 s of silence (`sine=d=1` concatenated with `anullsrc` for 5 s);
  - run your trim helper on it;
  - print the result duration. It should be about 1.3 s.
- Report the output.
