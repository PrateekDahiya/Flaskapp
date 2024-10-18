from flask import Flask, request, jsonify
from flask_cors import CORS
import yt_dlp
from yt_dlp.utils import ExtractorError, DownloadError

app = Flask(__name__)
CORS(app)

def get_video_qualities(video_url):
    ydl_opts = {
        'quiet': 'false',  # Run in quiet mode
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best',  # Get the best video+audio combo
        'nocheckcertificate': True,  # Skip certificate checks for faster response
        'verbose': True,
        'noplaylist': True,  # Prevent downloading playlists for speed
        'sleep_interval': 0,  # Disable sleep interval for faster processing
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(video_url, download=False)
            formats = info_dict.get('formats', [])

            video_quality_map = {}
            best_audio = None
            highest_bitrate = 0

            # Process formats
            for f in formats:
                if f.get('vcodec') != 'none':  # Only videos
                    resolution = f.get('height')
                    if resolution is not None and resolution not in video_quality_map:
                        video_quality_map[resolution] = f.get('url')
                elif f.get('acodec') != 'none' and f.get('abr') is not None:
                    bitrate = f.get('abr')
                    if bitrate > highest_bitrate:
                        highest_bitrate = bitrate
                        best_audio = f.get('url')

            # Collect available video resolutions
            video_quality_list = [{"resolution": res, "url": url} for res, url in video_quality_map.items()]

            # Get the best video URL
            best_video_url = formats[0]['url'] if formats else None

            return video_quality_list, best_audio, best_video_url

    except (ExtractorError, DownloadError) as e:
        print(f"Error extracting video info: {e}")
        return None, None, None

def get_video_url_by_quality(video_list, selected_quality):
    if not video_list:
        return None

    selected_resolution = selected_quality.rstrip('p')
    for video in video_list:
        resolution = str(video['resolution']).rstrip('p') if video['resolution'] else None
        if resolution == selected_resolution:
            return video['url']
    return None

@app.route('/get_video_url', methods=['GET'])
def get_video_url():
    video_id = request.args.get('video_id')
    quality = request.args.get('quality')
    
    if not video_id:
        return jsonify({"error": "Video ID must be provided"}), 400

    video_url = f'https://www.youtube.com/watch?v={video_id}'
    video_qualities, best_audio_url, best_video_url = get_video_qualities(video_url)

    if video_qualities is None and best_audio_url is None and best_video_url is None:
        return jsonify({"error": "Video is unavailable or restricted"}), 404

    if quality:
        selected_video_url = get_video_url_by_quality(video_qualities, quality)
        if selected_video_url:
            return jsonify({
                "selected_video_url": selected_video_url,
                "best_audio_url": best_audio_url,
                "best_video_url": best_video_url,
                "video_quality_options": video_qualities
            })
        else:
            return jsonify({"error": f"No URL found for {quality}"}), 404
    else:
        return jsonify({
            "best_audio_url": best_audio_url,
            "best_video_url": best_video_url,
            "video_quality_options": video_qualities
        })

@app.route('/keep-alive', methods=['GET'])
def keep_alive():
    return jsonify({"success": True})

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8111)
