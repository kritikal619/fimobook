"""Build one progressive H.264 stream for each opening + scoreboard sequence.

Run manually with ffmpeg installed. The browser keeps the same decoder/source
through the reveal and seeks to the keyframe at 7s when the scoreboard repeats.
"""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
VIDEOS = ROOT / 'static/pack-opener/videos'
OUTPUT = VIDEOS / 'cinematic-v1'


def build(intro):
    scoreboard = intro.with_name(intro.name.replace('_1.mp4', '_2.mp4'))
    target = OUTPUT / intro.name.replace('_1.mp4', '_cinematic.mp4')
    subprocess.run([
        'ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
        '-i', str(intro), '-stream_loop', '4', '-i', str(scoreboard),
        '-filter_complex',
        '[0:v]fps=30,scale=1024:768,setsar=1,tpad=stop_mode=clone:stop_duration=1,'
        'trim=duration=7,setpts=PTS-STARTPTS[a];'
        '[1:v]fps=30,scale=1024:768,setsar=1,trim=duration=12,setpts=PTS-STARTPTS[b];'
        '[a][b]concat=n=2:v=1:a=0[v]',
        '-map', '[v]', '-an', '-c:v', 'libx264', '-preset', 'veryfast',
        '-crf', '24', '-profile:v', 'baseline', '-level:v', '3.1',
        '-pix_fmt', 'yuv420p', '-maxrate', '2400k', '-bufsize', '4800k',
        '-g', '30', '-keyint_min', '30', '-sc_threshold', '0',
        '-force_key_frames', '7', '-threads', '2', '-movflags', '+faststart',
        str(target),
    ], check=True)
    print(f'{target.name}: {target.stat().st_size:,} bytes', flush=True)


if __name__ == '__main__':
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(build, sorted(VIDEOS.glob('packopening_*_1.mp4'))))
