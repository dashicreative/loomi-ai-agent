# TikTok Parser - Proof of Concept

Audio extraction and transcription for TikTok recipe videos.

## Status: Steps 1-4 Complete ✅

This proof of concept implements the first 4 steps of the TikTok parsing pipeline:

1. ✅ Receive TikTok URL
2. ✅ Call Apify TikTok Audio Downloader actor
3. ✅ Download audio as MP3
4. ✅ Upload to Deepgram for transcription
5. ⏸️ LLM recipe parsing (not yet implemented)
6. ⏸️ Quality control & JSON structuring (not yet implemented)

## Quick Start

### Run the test:

```bash
cd /Users/agustin/Desktop/loomi_ai_agent/Single_URL_Parsers/TikTok_Parser/test
python3 Test_TikTok_Parser.py
```

### You'll be prompted for a TikTok URL:

```
Enter TikTok URL: https://www.tiktok.com/@user/video/123456789
```

## What It Does

The test script will:

- 📱 Call Apify to extract TikTok audio metadata
- 🎵 Download the audio file from TikTok CDN (must be fresh URL)
- 🎙️ Transcribe with Deepgram Nova-2
- 📝 Print the full transcript
- 🗑️ Clean up temporary files

## Requirements

- `APIFY_API_KEY` in `.env` file
- `DEEPGRAM_WISPER_API` in `.env` file
- `deepgram-sdk` Python package installed

## Architecture

Based on Instagram parser flow:

```
TikTok URL → Apify → Audio Download → Deepgram → Transcript
```

## Next Steps

- [ ] Implement LLM recipe parsing (steps 5-6)
- [ ] Integrate shared Recipe_Quality_Control module
- [ ] Add to api.py as `/parse-tiktok-recipe` endpoint
- [ ] Update Cloud Function to route TikTok URLs

## Notes

⚠️ **TikTok audio URLs expire quickly (5-15 minutes)**
The script downloads immediately after Apify returns the URL.

✅ **No anti-bot issues detected**
Apify handles authentication and provides clean audio URLs.
