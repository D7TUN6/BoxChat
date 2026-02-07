"""
File handling functions
"""
import os
import uuid
from werkzeug.utils import secure_filename
from PIL import Image
from config import ALLOWED_EXTENSIONS, IMAGE_EXTENSIONS, MUSIC_EXTENSIONS, VIDEO_EXTENSIONS


def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def is_image_file(filename):
    """Check if file is an image"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in IMAGE_EXTENSIONS


def is_music_file(filename):
    """Check if file is audio"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in MUSIC_EXTENSIONS


def is_video_file(filename):
    """Check if file is a video"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in VIDEO_EXTENSIONS


def save_uploaded_file(file, subfolder='files', upload_folder='uploads'):
    """
    Save uploaded file to subfolder with UUID prefix
    
    Args:
        file: Flask FileStorage object
        subfolder: subdirectory name (avatars, files, music, etc.)
        upload_folder: base upload folder path (default 'uploads')
    
    Returns:
        str: URL path to saved file, or None if failed
    """
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4()}_{filename}"
        filepath = os.path.join(upload_folder, subfolder, unique_filename)
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        
        file.save(filepath)
        
        # Process stickers: make square thumbnail
        if subfolder == 'stickers' and is_image_file(file.filename):
            try:
                img = Image.open(filepath)
                size = min(img.size)
                img = img.crop((0, 0, size, size))
                img.thumbnail((256, 256), Image.Resampling.LANCZOS)
                img.save(filepath)
            except Exception as e:
                print(f"Error processing sticker: {e}")
        
        return f"/uploads/{subfolder}/{unique_filename}"
    
    return None


def resize_image(filepath, max_size=(32, 32)):
    """
    Resize image to fit within max_size while maintaining aspect ratio
    
    Args:
        filepath: path to image file
        max_size: tuple of (width, height)
    """
    try:
        img = Image.open(filepath)
        img.thumbnail(max_size, Image.Resampling.LANCZOS)
        img.save(filepath)
    except Exception as e:
        print(f"Error resizing image: {e}")
