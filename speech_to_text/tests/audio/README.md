# Test audio

`danish_two_speakers.wav` (16 kHz mono, ~10 s) is used by `python -m transcribe.selftest`
to check that the transcription pipeline recognises Danish speech and separates speakers.
It contains no project data. It was stitched together from short pronunciation recordings
on Wikimedia Commons, normalised in loudness, with silence between them:

| order | file on Commons | words | author | license |
| - | - | - | - | - |
| 1 | [Da-jeg ved det ikke.ogg](https://commons.wikimedia.org/wiki/File:Da-jeg_ved_det_ikke.ogg) | "jeg ved det ikke" | Kip (Nordjylland) | CC BY 4.0 |
| 2 | [Da-det ved jeg sgu ikke.ogg](https://commons.wikimedia.org/wiki/File:Da-det_ved_jeg_sgu_ikke.ogg) | "det ved jeg sgu ikke" | Kip (Nordjylland) | CC BY 4.0 |
| 3 | [Da-Fader Vor.ogg](https://commons.wikimedia.org/wiki/File:Da-Fader_Vor.ogg) | "Fader Vor" | Kip (Nordjylland) | CC BY 4.0 |
| 4 | [Da-hej.ogg](https://commons.wikimedia.org/wiki/File:Da-hej.ogg) | "hej" | Thrane | CC BY-SA 3.0 |
| 5 | [Da-behandling.ogg](https://commons.wikimedia.org/wiki/File:Da-behandling.ogg) | "behandling" | Kip (Nordjylland) | CC BY 4.0 |

Speaker A (Kip) speaks first, speaker B (Thrane) says "hej", then speaker A again.
The combined file is a derivative work and is shared under
[CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/).

To add your own (non-sensitive!) test clip, drop any audio file into this folder; the
self-test runs every file here and reports the recognised text and speaker count.
