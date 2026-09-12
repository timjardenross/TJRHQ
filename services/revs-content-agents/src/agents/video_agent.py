import subprocess
import wave
from pathlib import Path

from PIL import Image

from src.parsing.schemas import DesignBrief
from src.utils.config import load_config


def _require(path: Path, produced_by: str) -> Path:
    if not path.exists():
        raise FileNotFoundError(
            f"VideoAgent needs {path} (produced by {produced_by}) - run that agent first"
        )
    return path


def _audio_duration_seconds(wav_path: Path) -> float:
    with wave.open(str(wav_path), "rb") as wf:
        return wf.getnframes() / wf.getframerate()


class VideoAgent:
    """Assembles an FFmpeg slideshow (no local GPU, so no AI-generated video
    scenes) from the poster/social images and podcast narration already
    produced for this concept, instead of MISSION_BRIEF.md's Stable Diffusion
    scene-generation path."""

    format_name = "videos"

    def generate(self, brief: DesignBrief, output_dir: Path) -> dict:
        out_dir = output_dir / self.format_name
        out_dir.mkdir(parents=True, exist_ok=True)
        video_config = load_config().get("video", {})

        hero = _require(output_dir / "posters" / f"{brief.concept_id}_hero.jpg", "PosterAgent")
        social_dir = output_dir / "social"
        social_images = sorted(social_dir.glob(f"{brief.concept_id}_*.png"))
        audio_path = _require(output_dir / "podcasts" / f"{brief.concept_id}.wav", "PodcastAgent")

        images = [hero] + social_images
        duration = _audio_duration_seconds(audio_path)
        per_image = duration / len(images)

        # ffmpeg's concat demuxer reuses the first file's decoder for the whole
        # stream - mixing the hero's JPEG with the socials' PNGs silently corrupts
        # everything after frame 1. Normalize every frame to PNG first.
        frames_dir = out_dir / f"_{brief.concept_id}_frames"
        frames_dir.mkdir(exist_ok=True)
        normalized = []
        for i, image in enumerate(images):
            frame_path = frames_dir / f"frame_{i:02d}.png"
            Image.open(image).convert("RGB").save(frame_path)
            normalized.append(frame_path)

        # Measured on this ffmpeg (6.1.1): it already honors the last file's
        # duration correctly. The commonly-cited "repeat the last file" concat
        # workaround for older ffmpeg versions instead ADDS a spurious extra
        # segment here - verified by direct comparison, do not reintroduce it.
        concat_list = out_dir / f"{brief.concept_id}_concat.txt"
        lines = []
        for frame in normalized:
            lines.append(f"file '{frame.resolve()}'")
            lines.append(f"duration {per_image:.3f}")
        concat_list.write_text("\n".join(lines), encoding="utf-8")

        # ffmpeg's scale/pad filters take "w:h", not "WxH"
        resolution = {"720p": "1280:720", "1080p": "1920:1080", "4k": "3840:2160"}.get(
            video_config.get("resolution", "1080p"), "1920:1080"
        )
        fps = video_config.get("fps", 30)
        silent_path = out_dir / f"{brief.concept_id}_silent.mp4"
        video_path = out_dir / f"{brief.concept_id}.mp4"

        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list),
             "-vf", f"scale={resolution}:force_original_aspect_ratio=decrease,"
                    f"pad={resolution}:(ow-iw)/2:(oh-ih)/2,format=yuv420p",
             "-r", str(fps), "-c:v", "libx264", str(silent_path)],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(silent_path), "-i", str(audio_path),
             "-c:v", "copy", "-c:a", "aac", "-shortest", str(video_path)],
            check=True, capture_output=True,
        )
        silent_path.unlink()
        concat_list.unlink()
        for frame in normalized:
            frame.unlink()
        frames_dir.rmdir()

        return {"format": self.format_name, "files": [str(video_path)]}
