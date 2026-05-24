import os
import re
import shutil
import zipfile
import json
from pathlib import Path
from datetime import datetime
from flask import Flask, render_template, jsonify, request, send_from_directory
from werkzeug.utils import secure_filename
from bs4 import BeautifulSoup

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # Limit uploads to 500MB

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
ZIPS_DIR = DATA_DIR / "zips"
MEDIA_DIR = DATA_DIR / "media"
PARSED_DIR = DATA_DIR / "parsed"

# User's external ZIP directory
USER_ZIPS_DIR = Path("D:/vscode/igchatexport/kjnskdjvbjksdbvsd")

# Ensure necessary directories exist
ZIPS_DIR.mkdir(parents=True, exist_ok=True)
MEDIA_DIR.mkdir(parents=True, exist_ok=True)
PARSED_DIR.mkdir(parents=True, exist_ok=True)

def sanitize_chat_name(name):
    """Sanitizes chat name for use in file systems and URLs."""
    if not name:
        return "unknown_chat"
    return re.sub(r'[^a-zA-Z0-9_]', '_', name.strip())

def extract_media(zip_path, chat_name, zip_id):
    """Extracts media files from the ZIP's media/ directory to the local folder."""
    safe_chat = sanitize_chat_name(chat_name)
    safe_zip = secure_filename(zip_id)
    target_media_dir = MEDIA_DIR / safe_chat / safe_zip
    target_media_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path, 'r') as z:
        for name in z.namelist():
            # Check for media folder inside zip
            if 'media/' in name and not name.endswith('/'):
                filename = os.path.basename(name)
                if not filename:
                    continue
                dest_path = target_media_dir / filename
                if dest_path.exists():
                    continue  # Skip if already extracted
                
                # Write safely
                with z.open(name) as source, open(dest_path, 'wb') as target:
                    shutil.copyfileobj(source, target)

def parse_zip_export(zip_path):
    """Parses a chat export ZIP file, extracts media, and caches metadata."""
    zip_filename = os.path.basename(zip_path)
    zip_id = os.path.splitext(zip_filename)[0]
    cache_path = PARSED_DIR / f"{secure_filename(zip_id)}.json"

    # If cache exists, load it
    if cache_path.exists():
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Verify it has all standard fields
                if all(k in data for k in ('chat_name', 'messages', 'message_count')):
                    return data
        except Exception as e:
            print(f"Error loading cache for {zip_filename}: {e}")

    # Parse ZIP file
    print(f"Parsing new ZIP file: {zip_filename}")
    with zipfile.ZipFile(zip_path, 'r') as z:
        # Discover and sort m4a voice note files numerically
        m4a_files = sorted(
            [f for f in z.namelist() if f.endswith('.m4a')],
            key=lambda f: int(re.search(r'media_(\d+)\.m4a', f).group(1)) if re.search(r'media_(\d+)\.m4a', f) else 999999
        )
        
        html_files = [f for f in z.namelist() if f.endswith('index.html')]
        if not html_files:
            print(f"Warning: No index.html found in {zip_filename}")
            return None
        
        index_html_path = html_files[0]
        html_content = z.read(index_html_path).decode('utf-8', errors='replace')
        
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Extract chat name
        title_tag = soup.find('title')
        chat_name = "Unknown Chat"
        if title_tag:
            chat_name = title_tag.text.replace(" - Instagram DM", "").strip()
        else:
            header_h1 = soup.find('header')
            if header_h1 and header_h1.find('h1'):
                chat_name = header_h1.find('h1').text.strip()

        chat_name = re.sub(r'\s*[-_]\s*\d{4}[-_]\d{2}[-_]\d{2}.+?\d{4}[-_]\d{2}[-_]\d{2}', '', chat_name)
        chat_name = chat_name.strip(" -_")
        
        # We need a sanitized version of chat name for routing and file path
        safe_chat_name = sanitize_chat_name(chat_name)

        messages_div = soup.find('div', class_='messages')
        if not messages_div:
            print(f"Warning: No messages container found in {zip_filename}")
            return None

        messages = []
        current_date_str = ""
        voice_index = 0
        
        # Iterate over direct children of the messages list
        for child in messages_div.children:
            if child.name != 'div':
                continue
                
            classes = child.get('class', [])
            if 'date-sep' in classes:
                span = child.find('span')
                if span:
                    current_date_str = span.text.strip()
            elif 'msg' in classes:
                # Sent or received
                direction = 'sent' if 'sent' in classes else 'recv'
                
                # Sender details (especially in groups)
                sender_name = None
                sender_pic = None
                sender_info_div = child.find('div', class_='sender-info')
                if sender_info_div:
                    sender_name_span = sender_info_div.find('span', class_='sender-name')
                    if sender_name_span:
                        sender_name = sender_name_span.text.strip()
                    sender_pic_img = sender_info_div.find('img', class_='sender-pic')
                    if sender_pic_img:
                        sender_pic = sender_pic_img.get('src')
                    else:
                        placeholder = sender_info_div.find('div', class_='sender-pic-placeholder')
                        if placeholder:
                            sender_pic = placeholder.text.strip()

                # Message bubble body HTML
                bubble_div = child.find('div', class_='bubble')
                bubble_html = ""
                if bubble_div:
                    # Look for voice elements and enrich them with the audio player HTML
                    voice_div = bubble_div.find('div', class_='voice')
                    if voice_div and voice_index < len(m4a_files):
                        m4a_filename = os.path.basename(m4a_files[voice_index])
                        custom_player_html = f'''
<div class="voice-player">
  <button class="voice-play-btn" aria-label="Play Voice Note" type="button">
    <svg class="play-icon" viewBox="0 0 24 24" fill="currentColor" style="width: 16px; height: 16px; display: block;">
      <path d="M8 5v14l11-7z"/>
    </svg>
    <svg class="pause-icon" viewBox="0 0 24 24" fill="currentColor" style="width: 16px; height: 16px; display: none;">
      <path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/>
    </svg>
  </button>
  <div class="voice-info">
    <span class="voice-label">Voice Note</span>
    <span class="voice-duration">Voice note</span>
  </div>
  <div class="voice-progress-container">
    <div class="voice-progress-bar">
      <div class="voice-progress-fill"></div>
    </div>
  </div>
  <audio src="VOICE_AUDIO_SRC_PLACEHOLDER" preload="none"></audio>
</div>
'''
                        voice_div.clear()
                        # Parse the custom player HTML
                        player_soup = BeautifulSoup(custom_player_html, 'html.parser')
                        voice_div.append(player_soup.div)
                        voice_index += 1

                    # Parse bubble inner content
                    bubble_html = str(bubble_div)
                    
                    # Rewrite media paths from local relative (media/...) to server dynamic routes
                    # e.g., media/media_0.jpg -> /media/chat_name/zip_id/media_0.jpg
                    media_url_prefix = f"/media/{safe_chat_name}/{secure_filename(zip_id)}/"
                    bubble_html = bubble_html.replace('media/', media_url_prefix)
                    
                    # Replace voice audio placeholder with correct route
                    if 'VOICE_AUDIO_SRC_PLACEHOLDER' in bubble_html:
                        audio_url = f"/media/{safe_chat_name}/{secure_filename(zip_id)}/{m4a_filename}"
                        bubble_html = bubble_html.replace('VOICE_AUDIO_SRC_PLACEHOLDER', audio_url)
                
                # Timestamp string (e.g., 07:22 PM)
                time_div = child.find('div', class_='time')
                time_str = ""
                if time_div:
                    time_str = time_div.text.strip()

                # Absolute timestamp parsing for exact chronology
                timestamp_iso = None
                if current_date_str and time_str:
                    try:
                        # Mon, May 24, 2026 07:22 PM
                        dt_str = f"{current_date_str} {time_str}"
                        dt_str = re.sub(r'\s+', ' ', dt_str).strip()
                        dt = datetime.strptime(dt_str, "%a, %b %d, %Y %I:%M %p")
                        timestamp_iso = dt.isoformat()
                    except Exception as e:
                        # Fallback
                        pass

                messages.append({
                    'direction': direction,
                    'sender_name': sender_name,
                    'sender_pic': sender_pic,
                    'bubble_html': bubble_html,
                    'time_str': time_str,
                    'date_str': current_date_str,
                    'timestamp': timestamp_iso
                })

        # Calculate timestamps min and max for sorting ZIPs
        valid_timestamps = [datetime.fromisoformat(m['timestamp']) for m in messages if m['timestamp']]
        min_ts = min(valid_timestamps).isoformat() if valid_timestamps else None
        max_ts = max(valid_timestamps).isoformat() if valid_timestamps else None

        zip_data = {
            'chat_name': chat_name,
            'safe_chat_name': safe_chat_name,
            'zip_id': zip_id,
            'zip_filename': zip_filename,
            'message_count': len(messages),
            'min_timestamp': min_ts,
            'max_timestamp': max_ts,
            'messages': messages
        }

        # Extract files from media/ in the ZIP
        extract_media(zip_path, chat_name, zip_id)

        # Cache parsed data as JSON
        try:
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(zip_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error saving cache for {zip_filename}: {e}")

        return zip_data

def get_processed_chats():
    """Scans ZIP files, processes any new ones, and aggregates data grouped by Chat Name."""
    # Find all ZIP files from both local and external directories, deduplicating by filename
    zip_files_dict = {}
    
    # 1. Scan external user directory
    if USER_ZIPS_DIR.exists() and USER_ZIPS_DIR.is_dir():
        for z_path in USER_ZIPS_DIR.glob("*.zip"):
            zip_files_dict[z_path.name] = z_path
            
    # 2. Scan local app zips directory (overrides/supplements)
    for z_path in ZIPS_DIR.glob("*.zip"):
        zip_files_dict[z_path.name] = z_path
        
    zip_files = list(zip_files_dict.values())
    
    # Process zip files
    zip_datas = []
    for z_path in zip_files:
        try:
            data = parse_zip_export(z_path)
            if data:
                zip_datas.append(data)
        except Exception as e:
            print(f"Error parsing ZIP file {z_path.name}: {e}")

    # Group ZIP data by sanitized chat name
    chats = {}
    for data in zip_datas:
        safe_chat = data['safe_chat_name']
        if safe_chat not in chats:
            chats[safe_chat] = {
                'chat_name': data['chat_name'],
                'safe_chat_name': safe_chat,
                'message_count': 0,
                'chunks': [],
                'min_ts': None,
                'max_ts': None
            }
        
        chats[safe_chat]['message_count'] += data['message_count']
        chats[safe_chat]['chunks'].append({
            'zip_id': data['zip_id'],
            'zip_filename': data['zip_filename'],
            'message_count': data['message_count'],
            'min_ts': data['min_timestamp'],
            'max_ts': data['max_timestamp']
        })

        # Calculate absolute chat time bounds
        if data['min_timestamp']:
            curr_min = datetime.fromisoformat(data['min_timestamp'])
            if not chats[safe_chat]['min_ts'] or curr_min < datetime.fromisoformat(chats[safe_chat]['min_ts']):
                chats[safe_chat]['min_ts'] = data['min_timestamp']
        if data['max_timestamp']:
            curr_max = datetime.fromisoformat(data['max_timestamp'])
            if not chats[safe_chat]['max_ts'] or curr_max > datetime.fromisoformat(chats[safe_chat]['max_ts']):
                chats[safe_chat]['max_ts'] = data['max_timestamp']

    # Pre-format date ranges for user display
    for c_id, chat in chats.items():
        min_d = datetime.fromisoformat(chat['min_ts']).strftime("%b %d, %Y") if chat['min_ts'] else "Unknown"
        max_d = datetime.fromisoformat(chat['max_ts']).strftime("%b %d, %Y") if chat['max_ts'] else "Unknown"
        chat['date_range'] = f"{min_d} to {max_d}" if min_d != "Unknown" else "No dates available"
        chat['chunk_count'] = len(chat['chunks'])

    return chats

# --- App Routes ---

@app.route('/')
def dashboard():
    """Renders the dashboard listing all active conversations and uploader."""
    chats = get_processed_chats()
    return render_template('dashboard.html', chats=chats.values())

@app.route('/upload', methods=['POST'])
def upload_file():
    """Handles async AJAX or standard multipart form uploads of exported chat ZIPs."""
    if 'files' not in request.files:
        return jsonify({'success': False, 'error': 'No files provided'}), 400
    
    files = request.files.getlist('files')
    saved_count = 0
    errors = []

    for file in files:
        if file.filename == '':
            continue
        if not file.filename.endswith('.zip'):
            errors.append(f"Skipped {file.filename}: Not a ZIP file")
            continue
        
        try:
            filename = secure_filename(file.filename)
            dest_path = ZIPS_DIR / filename
            file.save(dest_path)
            saved_count += 1
            # Proactively trigger processing in the background
            parse_zip_export(dest_path)
        except Exception as e:
            errors.append(f"Failed to save {file.filename}: {str(e)}")

    if saved_count > 0:
        return jsonify({
            'success': True, 
            'message': f"Successfully uploaded and parsed {saved_count} file(s).",
            'errors': errors
        })
    else:
        return jsonify({
            'success': False, 
            'error': 'No valid ZIP files were uploaded.',
            'errors': errors
        }), 400

@app.route('/chat/<safe_chat_name>')
def chat_viewer(safe_chat_name):
    """Renders the viewer interface. Loads chat structure shell."""
    chats = get_processed_chats()
    if safe_chat_name not in chats:
        return "Chat not found", 404
    return render_template('viewer.html', chat=chats[safe_chat_name])

@app.route('/api/chat/<safe_chat_name>')
def get_chat_messages(safe_chat_name):
    """API endpoint returning merged, deduplicated, chronologically sorted messages for a chat."""
    # Find all cached parsed JSON files for this chat name
    parsed_files = list(PARSED_DIR.glob("*.json"))
    chat_chunks = []
    
    for p_path in parsed_files:
        try:
            with open(p_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if data.get('safe_chat_name') == safe_chat_name:
                    chat_chunks.append(data)
        except Exception as e:
            print(f"Error loading parse file {p_path.name}: {e}")

    if not chat_chunks:
        return jsonify({'success': False, 'error': 'No data found for this chat.'}), 404

    # 1. Sort chunk containers chronologically by their minimum timestamp
    # If a chunk has no timestamp bounds, place it at the end
    chat_chunks.sort(key=lambda chunk: chunk['min_timestamp'] or "9999-12-31")

    # 2. Gather and sort messages using stability sorting keys
    all_messages = []
    for chunk_index, chunk in enumerate(chat_chunks):
        for msg_index, msg in enumerate(chunk['messages']):
            # Enrich message with metadata to preserve absolute order
            msg['zip_id'] = chunk['zip_id']
            msg['chunk_index'] = chunk_index
            msg['msg_index'] = msg_index
            all_messages.append(msg)

    # 3. Deduplicate overlapping messages across chunks
    seen_signatures = set()
    unique_messages = []
    for msg in all_messages:
        # Deduplication signature: direction, sender, date, time, and content hash
        # To avoid minor formatting changes, we strip text inside bubble_html
        clean_bubble = re.sub(r'\s+', ' ', msg['bubble_html']).strip()
        sig = (
            msg['direction'],
            msg['sender_name'],
            msg['date_str'],
            msg['time_str'],
            clean_bubble
        )
        if sig not in seen_signatures:
            seen_signatures.add(sig)
            unique_messages.append(msg)

    # 4. Strict chronological sorting using stable keys:
    # A. Message timestamp (if parsed successfully)
    # B. Chunk relative index
    # C. Message relative index inside its original ZIP
    def get_sort_key(msg):
        ts = datetime.fromisoformat(msg['timestamp']) if msg['timestamp'] else datetime.min
        return (ts, msg['chunk_index'], msg['msg_index'])

    unique_messages.sort(key=get_sort_key)

    # Gather clean list for output
    messages_out = []
    for msg in unique_messages:
        messages_out.append({
            'direction': msg['direction'],
            'sender_name': msg['sender_name'],
            'sender_pic': msg['sender_pic'],
            'bubble_html': msg['bubble_html'],
            'time_str': msg['time_str'],
            'date_str': msg['date_str']
        })

    # Find name and bounds
    chat_title = chat_chunks[0]['chat_name']
    
    return jsonify({
        'success': True,
        'chat_name': chat_title,
        'message_count': len(messages_out),
        'messages': messages_out
    })

@app.route('/media/<safe_chat_name>/<zip_id>/<filename>')
def serve_media(safe_chat_name, zip_id, filename):
    """Dynamically and securely serves media items from local dynamic paths."""
    safe_chat = sanitize_chat_name(safe_chat_name)
    safe_zip = secure_filename(zip_id)
    safe_file = secure_filename(filename)
    
    media_folder = MEDIA_DIR / safe_chat / safe_zip
    if not media_folder.exists():
        return "Media file not found", 404
        
    return send_from_directory(media_folder, safe_file)

if __name__ == '__main__':
    # Print welcome status
    print("*" * 60)
    print("Instagram DM Export Joiner Started Successfully!")
    print("Place your export ZIP files in 'data/zips/' directory,")
    print("or upload them via the web dashboard.")
    print("Navigate to http://127.0.0.1:5000 in your browser to view.")
    print("*" * 60)
    
    app.run(debug=True, host='127.0.0.1', port=5000)
