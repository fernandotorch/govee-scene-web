# Task: Normalize non-OGG audio files on export in govee_controller.py

**File to edit:** `govee_controller.py`

Add `import tempfile` to the imports at the top of the file if it is not already there.

In the `export_pack` function, find this block that writes audio files into the zip:

```python
                ext = os.path.splitext(audio_path)[1].lower()
                if ext not in ['.ogg', '.wav', '.mp3', '.flac']:
                    warnings.append(f'Unsupported format: {info["file"]}')
                    continue
                file_size_mb = os.path.getsize(audio_path) / (1024 * 1024)
                if file_size_mb > 20:
                    warnings.append(f'Too large ({file_size_mb:.0f} MB): {info["file"]} — convert to MP3 first')
                    continue
                base_id = re.sub(r'\.(ogg|wav|mp3|flac)$', '', audio_id, flags=re.IGNORECASE)
                out_name = base_id + ext
                z.write(audio_path, out_name)
                info['file'] = out_name
```

Replace it with:

```python
                ext = os.path.splitext(audio_path)[1].lower()
                if ext not in ['.ogg', '.wav', '.mp3', '.flac']:
                    warnings.append(f'Unsupported format: {info["file"]}')
                    continue
                file_size_mb = os.path.getsize(audio_path) / (1024 * 1024)
                if ext == ".ogg" and file_size_mb > 20:
                    warnings.append(f"Large OGG ({file_size_mb:.0f} MB): {info['file']} — consider shorter loop")
                elif ext != ".ogg" and file_size_mb > 100:
                    warnings.append(f"Large {ext[1:].upper()} ({file_size_mb:.0f} MB): {info['file']} — converting to OGG...")
                
                base_id = re.sub(r'\.(ogg|wav|mp3|flac)$', '', audio_id, flags=re.IGNORECASE)
                if ext == '.ogg':
                    z.write(audio_path, base_id + '.ogg')
                    info['file'] = base_id + '.ogg'
                else:
                    tmp_fd, tmp_path = tempfile.mkstemp(suffix='.ogg')
                    os.close(tmp_fd)
                    try:
                                                subprocess.run([
                            "ffmpeg", "-y", "-i", audio_path,
                            "-af", "loudnorm=I=-14:TP=-1:LRA=11",
                            "-c:a", "libvorbis", "-q:a", "4",
                            tmp_path
                        ], check=True, capture_output=True)
                        new_size_mb = os.path.getsize(tmp_path) / (1024 * 1024)
                        if new_size_mb > 20:
                            warnings.append(f"Still large after conversion ({new_size_mb:.0f} MB): {info['file']}")
                        z.write(tmp_path, base_id + ".ogg")
                        info["file"] = base_id + ".ogg" 
                    finally:
                        os.unlink(tmp_path)
```

No other changes.
