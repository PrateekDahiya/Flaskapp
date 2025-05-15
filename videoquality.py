from flask import Flask, request, jsonify
from flask_cors import CORS
import youtube_dl
import logging
import os
import json
import random
import time

app = Flask(__name__)
CORS(app)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_video_qualities(video_url, max_retries=3):
    try:
        for attempt in range(max_retries):
            try:
                logger.info(f"Attempt {attempt + 1}/{max_retries} to extract video info")
                
                # Configure youtube-dl options
                ydl_opts = {
                    'format': 'best',  # Download the best quality
                    'quiet': True,
                    'no_warnings': True,
                    'extract_flat': True,  # Extract info without downloading
                }
                
                with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(video_url, download=False)
                    
                    if not info:
                        logger.error("Failed to extract video info")
                        return None, None, None
                    
                    # Extract video qualities
                    video_quality_list = []
                    best_audio_url = None
                    best_video_url = None
                    
                    # Get the best video URL
                    if 'url' in info:
                        best_video_url = info['url']
                    
                    # Get the best audio URL (if available)
                    if 'requested_formats' in info:
                        for fmt in info['requested_formats']:
                            if fmt.get('acodec') != 'none' and fmt.get('vcodec') == 'none':
                                best_audio_url = fmt.get('url')
                                break
                    
                    # Extract video qualities
                    if 'formats' in info:
                        for fmt in info['formats']:
                            if fmt.get('height') and fmt.get('url'):
                                video_quality_list.append({
                                    "resolution": f"{fmt['height']}p",
                                    "url": fmt['url']
                                })
                    
                    logger.info(f"Found {len(video_quality_list)} video qualities")
                    return video_quality_list, best_audio_url, best_video_url
                    
            except Exception as e:
                logger.error(f"Attempt {attempt + 1} failed: {str(e)}")
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    logger.info(f"Waiting {wait_time} seconds before retrying...")
                    time.sleep(wait_time)
                    continue
                raise
                
    except Exception as e:
        logger.error(f"Error in get_video_qualities: {str(e)}")
        return None, None, None

def get_video_url_by_quality(video_list, selected_quality):
    if not video_list:
        return None

    selected_resolution = selected_quality.rstrip('p')  # Remove 'p' from resolution if present
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
    logger.info(f"Processing request for video ID: {video_id}")
    
    try:
        video_qualities, best_audio_url, best_video_url = get_video_qualities(video_url)

        if video_qualities is None and best_audio_url is None and best_video_url is None:
            logger.error(f"Failed to extract video information for ID: {video_id}")
            return jsonify({
                "error": "Video is unavailable or restricted",
                "video_id": video_id,
                "message": "Could not extract video information. The video might be private, restricted, or unavailable in your region."
            }), 404

        response_data = {
            "best_audio_url": best_audio_url,
            "best_video_url": best_video_url,
            "video_quality_options": video_qualities
        }

        if quality:
            selected_video_url = get_video_url_by_quality(video_qualities, quality)
            if selected_video_url:
                response_data["selected_video_url"] = selected_video_url
            else:
                logger.warning(f"Requested quality {quality} not found for video ID: {video_id}")
                return jsonify({
                    "error": f"No URL found for quality {quality}",
                    "video_id": video_id,
                    "available_qualities": [q["resolution"] for q in video_qualities]
                }), 404

        return jsonify(response_data)

    except Exception as e:
        logger.error(f"Unexpected error processing video ID {video_id}: {str(e)}")
        return jsonify({
            "error": "An unexpected error occurred",
            "video_id": video_id,
            "message": str(e)
        }), 500

@app.route('/keep-alive', methods=['GET'])
def keep_alive():
    return jsonify({"success": True})

@app.route('/get-short-url', methods=['GET'])
def get_short_url():
    video_id = request.args.get('video_id')
    if not video_id:
        return jsonify({"error": "Video ID must be provided"}), 400

    video_url = f'https://www.youtube.com/watch?v={video_id}'
    _, _, best_video_url = get_video_qualities(video_url)

    if best_video_url is None:
        return jsonify({"error": "Video is unavailable or restricted"}), 404

    return jsonify({"stream_url": best_video_url})

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8111)
