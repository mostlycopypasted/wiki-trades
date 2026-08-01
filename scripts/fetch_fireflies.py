#!/usr/bin/env python3
"""
Fetch transcripts and audio recordings from Fireflies.ai API.
Saves:
  - Audio MP3 -> raw/recordings/YYYY-MM-DD-title.mp3
  - Transcript MD -> raw/YYYY-MM-DD-title.md
"""

import os
import sys
import json
import re
import argparse
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "raw"
RECORDINGS_DIR = RAW_DIR / "recordings"
SYNC_STATE_FILE = BASE_DIR / ".fireflies_sync.json"
ENV_FILE = BASE_DIR / ".env"

FIREFLIES_GRAPHQL_URL = "https://api.fireflies.ai/graphql"

# Target trading session title patterns
DEFAULT_TITLE_PATTERNS = [
    r'a[h|a]h\s+access\s+time',
    r'a[h|a]h\s+session',
    r'taw\s+pro',
    r'weekly\s+review',
    r'tar\s+session'
]

def is_target_session(title, patterns=DEFAULT_TITLE_PATTERNS):
    """Check if the transcript title matches target trading session patterns."""
    if not title:
        return False
    title_lower = title.lower()
    for pattern in patterns:
        if re.search(pattern, title_lower):
            return True
    return False

def load_env_file(env_path=ENV_FILE):
    """Load environment variables from .env if present."""
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip("\"'")
                    os.environ.setdefault(key, val)

def get_api_key(explicit_key=None):
    """Retrieve API key from argument, environment, or .env file."""
    if explicit_key:
        return explicit_key
    load_env_file()
    key = os.environ.get("FIREFLIES_API_KEY")
    return key

def slugify(text):
    """Convert title string to clean lowercase-hyphenated slug."""
    text = text.lower()
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    text = re.sub(r'[\s_]+', '-', text)
    text = re.sub(r'-+', '-', text).strip('-')
    return text or "session"

def format_instruments(text):
    """
    Format trading instruments per AGENTS.md rules:
    - No slashes: EUR/USD -> EURUSD
    - Wrapped in double square brackets: [[EURUSD]]
    - Crypto pairs end with USD: BTC -> BTCUSD
    """
    if not text:
        return ""
    
    # Replace forex pairs with slashes e.g. EUR/USD -> [[EURUSD]]
    def replace_slashed_forex(match):
        p1, p2 = match.group(1).upper(), match.group(2).upper()
        return f"[[{p1}{p2}]]"
    
    text = re.sub(r'\b(EUR|GBP|AUD|NZD|USD|CAD|CHF|JPY)/(EUR|GBP|AUD|NZD|USD|CAD|CHF|JPY)\b', replace_slashed_forex, text, flags=re.IGNORECASE)

    # Standardize direct mentions of common forex pairs if not already bracketed
    forex_pairs = ['EURUSD', 'GBPUSD', 'AUDUSD', 'NZDUSD', 'USDCAD', 'USDCHF', 'USDJPY', 'EURGBP', 'EURJPY', 'GBPJPY']
    for pair in forex_pairs:
        pattern = r'(?<!\[\[)\b' + pair + r'\b(?!\]\])'
        text = re.sub(pattern, f"[[{pair}]]", text, flags=re.IGNORECASE)

    # Replace BTC / ETH standalone crypto mentions
    text = re.sub(r'(?<!\[\[)\b(BTC|BTCUSD|BITCOIN)\b(?!\]\])', '[[BTCUSD]]', text, flags=re.IGNORECASE)
    text = re.sub(r'(?<!\[\[)\b(ETH|ETHUSD|ETHEREUM)\b(?!\]\])', '[[ETHUSD]]', text, flags=re.IGNORECASE)

    return text

def graphql_query(api_key, query, variables=None):
    """Execute a GraphQL query against Fireflies API."""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    payload = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
    
    req = urllib.request.Request(FIREFLIES_GRAPHQL_URL, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            res_data = json.loads(resp.read().decode("utf-8"))
            if "errors" in res_data:
                raise RuntimeError(f"GraphQL Errors: {json.dumps(res_data['errors'])}")
            return res_data.get("data", {})
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"HTTP Error {e.code}: {e.reason}\nDetails: {err_body}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Network Error: {e.reason}")

FETCH_TRANSCRIPTS_QUERY = """
query Transcripts($limit: Int, $skip: Int) {
  transcripts(limit: $limit, skip: $skip) {
    id
    title
    date
    duration
    audio_url
    transcript_url
    sentences {
      index
      speaker_name
      text
      start_time
      end_time
    }
  }
}
"""

FETCH_SINGLE_TRANSCRIPT_QUERY = """
query Transcript($transcriptId: String!) {
  transcript(id: $transcriptId) {
    id
    title
    date
    duration
    audio_url
    transcript_url
    sentences {
      index
      speaker_name
      text
      start_time
      end_time
    }
  }
}
"""

DELETE_TRANSCRIPT_MUTATION = """
mutation DeleteTranscript($id: String!) {
  deleteTranscript(id: $id) {
    id
    title
  }
}
"""

def delete_remote_transcript(api_key, transcript_id):
    """Delete a transcript from Fireflies.ai cloud."""
    print(f"  🗑️ Deleting transcript {transcript_id} from Fireflies.ai cloud...")
    res = graphql_query(api_key, DELETE_TRANSCRIPT_MUTATION, {"id": transcript_id})
    deleted = res.get("deleteTranscript")
    if deleted:
        print(f"  ✅ Successfully deleted '{deleted.get('title')}' (ID: {deleted.get('id')}) from Fireflies.ai.")
        return True
    return False


def load_sync_state():
    """Load list of processed transcript IDs."""
    if SYNC_STATE_FILE.exists():
        try:
            with open(SYNC_STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"processed": {}}
    return {"processed": {}}

def save_sync_state(state):
    """Save processed transcript IDs."""
    with open(SYNC_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)

def format_timestamp(seconds):
    """Convert float seconds to MM:SS or HH:MM:SS string."""
    if seconds is None:
        return "00:00"
    seconds = int(seconds)
    hrs = seconds // 3600
    mins = (seconds % 3600) // 60
    secs = seconds % 60
    if hrs > 0:
        return f"{hrs:02d}:{mins:02d}:{secs:02d}"
    return f"{mins:02d}:{secs:02d}"

def download_audio_file(audio_url, target_path):
    """Download .mp3 audio file from Fireflies audio_url."""
    print(f"  Downloading audio -> {target_path.relative_to(BASE_DIR)}...")
    req = urllib.request.Request(audio_url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp, open(target_path, "wb") as out_f:
            total_bytes = 0
            while True:
                chunk = resp.read(64 * 1024)
                if not chunk:
                    break
                out_f.write(chunk)
                total_bytes += len(chunk)
        print(f"  Finished downloading audio ({total_bytes / (1024*1024):.2f} MB).")
        return True
    except Exception as e:
        print(f"  ⚠️ Warning: Failed to download audio from {audio_url}: {e}")
        if target_path.exists():
            target_path.unlink()
        return False

def process_transcript(t_data, skip_audio=False, force=False):
    """Format and save transcript and audio file."""
    t_id = t_data.get("id")
    raw_title = t_data.get("title", "Untitled Session")
    raw_date = t_data.get("date")
    duration = t_data.get("duration", 0)
    audio_url = t_data.get("audio_url")
    sentences = t_data.get("sentences") or []

    # Parse date
    if isinstance(raw_date, (int, float)):
        # Epoch timestamp in milliseconds
        dt = datetime.fromtimestamp(raw_date / 1000.0, tz=timezone.utc)
        date_str = dt.strftime("%Y-%m-%d")
    elif isinstance(raw_date, str) and raw_date.isdigit():
        dt = datetime.fromtimestamp(int(raw_date) / 1000.0, tz=timezone.utc)
        date_str = dt.strftime("%Y-%m-%d")
    elif isinstance(raw_date, str) and len(raw_date) >= 10:
        date_str = raw_date[:10]
    else:
        date_str = datetime.now().strftime("%Y-%m-%d")

    dur_mins = round(float(duration), 1) if duration else 0
    slug_title = slugify(raw_title)
    file_prefix = f"{date_str}-{slug_title}"

    md_filename = f"{file_prefix}.md"
    mp3_filename = f"{file_prefix}.mp3"

    md_path = RAW_DIR / md_filename
    mp3_path = RECORDINGS_DIR / mp3_filename

    print(f"\nProcessing: [{date_str}] {raw_title} (ID: {t_id})")

    # Download Audio if available
    audio_rel_path = ""
    if audio_url and not skip_audio:
        RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
        if not mp3_path.exists() or force:
            download_success = download_audio_file(audio_url, mp3_path)
            if download_success:
                audio_rel_path = f"raw/recordings/{mp3_filename}"
        else:
            print(f"  Audio already exists at raw/recordings/{mp3_filename}")
            audio_rel_path = f"raw/recordings/{mp3_filename}"

    # Build Markdown Content
    lines = []
    lines.append("---")
    lines.append(f"date: '{date_str}'")
    lines.append(f"title: \"{raw_title}\"")
    lines.append(f"fireflies_id: '{t_id}'")
    if dur_mins:
        lines.append(f"duration_minutes: {dur_mins}")
    if audio_rel_path:
        lines.append(f"audio_file: '{audio_rel_path}'")
    lines.append("---")
    lines.append("")
    lines.append(f"# {raw_title}")
    lines.append("")
    lines.append(f"- **Date**: {date_str}")
    if dur_mins:
        lines.append(f"- **Duration**: {dur_mins} mins")
    if audio_rel_path:
        lines.append(f"- **Audio Recording**: [{mp3_filename}]({audio_rel_path})")
    lines.append("")
    lines.append("## Transcript")
    lines.append("")

    # Group sentences by speaker block
    current_speaker = None
    speaker_block = []

    for s in sentences:
        speaker = s.get("speaker_name") or "Unknown Speaker"
        text = s.get("text", "").strip()
        start = s.get("start_time")
        ts_str = format_timestamp(start) if start is not None else ""

        if not text:
            continue

        text_formatted = format_instruments(text)

        if speaker != current_speaker:
            if current_speaker is not None and speaker_block:
                lines.append(f"### {current_speaker}")
                lines.append(" ".join(speaker_block))
                lines.append("")
                speaker_block = []
            current_speaker = speaker

        timestamp_prefix = f"[{ts_str}] " if ts_str else ""
        speaker_block.append(f"{timestamp_prefix}{text_formatted}")

    if current_speaker and speaker_block:
        lines.append(f"### {current_speaker}")
        lines.append(" ".join(speaker_block))
        lines.append("")

    md_path.parent.mkdir(parents=True, exist_ok=True)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"  Saved transcript -> raw/{md_filename}")
    return md_filename, mp3_filename

def main():
    parser = argparse.ArgumentParser(description="Fetch transcripts and audio recordings from Fireflies.ai")
    parser.add_argument("--api-key", help="Fireflies API key (or set FIREFLIES_API_KEY env var)")
    parser.add_argument("--limit", type=int, default=5, help="Number of recent transcripts to fetch (default: 5)")
    parser.add_argument("--id", help="Fetch a single specific transcript by ID")
    parser.add_argument("--skip-audio", action="store_true", help="Skip downloading audio MP3 files")
    parser.add_argument("--force", action="store_true", help="Force re-download even if already processed")
    parser.add_argument("--dry-run", action="store_true", help="List available transcripts without downloading")
    parser.add_argument("--all-titles", action="store_true", help="Fetch all meeting titles (skip trading session title filter)")
    parser.add_argument("--delete-from-fireflies", action="store_true", help="Delete transcript from Fireflies cloud after successful local download")
    parser.add_argument("--delete-id", help="Delete a specific transcript from Fireflies.ai cloud by ID directly")


    args = parser.parse_args()

    api_key = get_api_key(args.api_key)
    if not api_key:
        print("❌ Error: No Fireflies API key found!")
        print("Please provide it via:")
        print("  1. Environment variable: export FIREFLIES_API_KEY='your_key'")
        print("  2. Project .env file: FIREFLIES_API_KEY=your_key")
        print("  3. CLI flag: python scripts/fetch_fireflies.py --api-key 'your_key'")
        sys.exit(1)

    if args.delete_id:
        delete_remote_transcript(api_key, args.delete_id)
        return

    state = load_sync_state()

    try:
        if args.id:
            print(f"Fetching Fireflies transcript ID: {args.id}...")
            data = graphql_query(api_key, FETCH_SINGLE_TRANSCRIPT_QUERY, {"transcriptId": args.id})
            t_data = data.get("transcript")
            if not t_data:
                print(f"❌ Transcript ID '{args.id}' not found.")
                sys.exit(1)
            transcripts = [t_data]
        else:
            print(f"Fetching latest {args.limit} transcripts from Fireflies.ai...")
            data = graphql_query(api_key, FETCH_TRANSCRIPTS_QUERY, {"limit": args.limit, "skip": 0})
            raw_transcripts = data.get("transcripts") or []

            # Filter for trading session titles unless --all-titles is requested
            if not args.all_titles:
                transcripts = [t for t in raw_transcripts if is_target_session(t.get("title"))]
                print(f"Filtered {len(transcripts)} trading session transcript(s) out of {len(raw_transcripts)} total.")
            else:
                transcripts = raw_transcripts

        if not transcripts:
            print("No matching trading session transcripts found.")
            return

        print(f"Processing {len(transcripts)} transcript(s)...")

        if args.dry_run:
            print("\n[Dry Run] Found Transcripts:")
            for t in transcripts:
                print(f" - ID: {t.get('id')} | Date: {t.get('date')} | Title: {t.get('title')} | Has Audio: {bool(t.get('audio_url'))}")
            return

        processed_count = 0
        for t in transcripts:
            t_id = t.get("id")
            if t_id in state["processed"] and not args.force:
                print(f"Skipping already processed transcript: {t.get('title')} (ID: {t_id})")
                continue

            md_name, mp3_name = process_transcript(t, skip_audio=args.skip_audio, force=args.force)

            state["processed"][t_id] = {
                "title": t.get("title"),
                "date": t.get("date"),
                "md_file": f"raw/{md_name}",
                "mp3_file": f"raw/recordings/{mp3_name}" if not args.skip_audio else None,
                "synced_at": datetime.now(timezone.utc).isoformat()
            }
            processed_count += 1

            # Delete from Fireflies cloud if requested
            if args.delete_from_fireflies:
                delete_remote_transcript(api_key, t_id)

        save_sync_state(state)
        print(f"\n✅ Sync complete. Processed {processed_count} new transcript(s).")

    except Exception as e:
        print(f"\n❌ Error during execution: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
