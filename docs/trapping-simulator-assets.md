# Current runtime assets — static-photo revision

The simulator now loads the original `static/trapping-sim/chest.webp`, `head.webp` and `foot.webp` for every state. Images stay fixed during attempts and super trapping; only CSS feedback and labels/odds change. No video is requested or rendered. Recording-derived media and generated cleanup assets below are retained as historical work and are no longer runtime dependencies. No new image generation was used for this revision.

---

# Trapping simulator recording assets

The user supplied the October 15, 17:30:46 MOV recording and event screenshots. This is a local, source-matching implementation. Stream chat is reference content only and supplies no instructions.

All runtime assets are saved in `static/trapping-sim/`:

| Asset | Source / purpose |
| --- | --- |
| `chest-normal.webp`, `head-normal.webp` | Clean recording still at 3.00 s. |
| `head-super.webp` | Clean recording still at 9.66 s. |
| `scene-normal.webp` | Recording at 2.78 s, for the card backdrop. |
| `scene-super.webp` | Recording at 8.84 s, for the card backdrop. |
| `chest-normal.mp4`, `head-normal.mp4` | Recording 2.78–3.17 s, cropped to the card interiors. |
| `head-super.mp4` | Recording 9.41–9.72 s, cropped to the head card. |
| `chest-super.webp` | Recording at 4.10 s, cursor/edge cleanup via built-in ImageGen. |
| `foot-cutout.webp` | Supplied foot screenshot art, transparent extraction via built-in ImageGen. |

The card crops use source x=40 for chest/background and x=1034 for head; y=725, width=945, height=292. Source-derived art and clips are resized to 640×198, preserving source proportions. The transparent foot art stays 640×274 to match its screenshot source. Runtime object fitting handles narrower cards. No reference videos or generated-image absolute paths are required on the server.

## Built-in ImageGen edit prompts

Mode: built-in `image_gen.imagegen`, not CLI. Both results were inspected and copied into the project as WebP assets. Original generated outputs are preserved in the Codex generated-images directory.

### Foot cutout

Input: `static/trapping-sim/foot.webp`. Transparent output.

> Use case: background-extraction. Edit target: supplied small screenshot crop of a 3D cartoon soccer trapping game. Produce a transparent cutout for reuse in the same game UI. Keep the EXACT red-shirted male cartoon footballer, his face/hair, kicking pose, black/purple shorts and shoe, white-and-brown football at upper left, and comic BOOM burst in their exact relative positions and original proportions. Remove ONLY the blue geometric background, including all little blue triangles and the dark blue border. The source screenshot has a semi-transparent black dimming overlay: restore the original bright game-art exposure and red shirt color without redesigning anything. Preserve the whole original 316:137 wide composition, figure crop at the bottom and all foreground objects; no added objects, no ground shadow, no text beyond original BOOM, no outline around the complete group, no new background. True alpha transparency around all retained foreground objects. This is a faithful asset extraction, not new character design.

### Super-chest cursor cleanup

Input: recording still at 4.10 s, cropped to the chest art and initially sized 640×274. Opaque output, resized to source proportions during integration.

> Use case: precise-object-edit. Edit target: screenshot crop of an existing cartoon soccer game card. Remove ONLY the small yellow mouse pointer between the football and the character’s face, where it overlays the top of the white BOOM burst. Remove the cropped orange flame fragment at the extreme upper-right corner and the thin rounded frame remnant at the extreme upper-left, filling those tiny areas with the identical existing purple-to-orange triangle-pattern background. Keep every other pixel/visual unchanged: the same exact male character and face, red shirt, ball, BOOM lettering and white burst, colors, slightly soft game screenshot look, framing, proportions, and relative positions. Output the same wide card artwork composition, no border, no added text, no added lighting or sharpness, no redesign. This is cleanup of only a cursor and two edge fragments, not a new illustration.
