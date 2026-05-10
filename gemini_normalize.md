# Task: Add loudness normalization to audio upload in govee_controller.py

**File to edit:** `govee_controller.py`

In the `upload_sfx` function, find this line:

```python
        subprocess.run(["ffmpeg", "-y", "-i", temp_path, "-c:a", "libvorbis", "-q:a", "4", output_path], check=True)
```

Replace it with:

```python
        subprocess.run([
            "ffmpeg", "-y", "-i", temp_path,
            "-af", "loudnorm=I=-14:TP=-1:LRA=11",
            "-c:a", "libvorbis", "-q:a", "4",
            output_path
        ], check=True)
```

No other changes.
