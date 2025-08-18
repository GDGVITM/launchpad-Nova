from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings
from django.http import HttpResponse, FileResponse, Http404
from django.views import View
import os
import mimetypes
from .utils import generate_animation_videos, generate_animation_json


class ManimView(APIView):
    def post(self, request):
        data = request.data
        prompt = data.get("prompt")
        
        try:
            animation_guide = generate_animation_json(prompt)
            video_path = generate_animation_videos(animation_guide)
            
            if video_path and os.path.exists(video_path):
                # Generate the downloadable URL
                # Get the filename from the full path
                filename = os.path.basename(video_path)
                # Create the media URL that can be accessed via browser
                video_url = f"{settings.MEDIA_URL}{filename}"
                
                # Get the host from the request to create absolute URL
                host = request.get_host()
                protocol = 'https' if request.is_secure() else 'http'
                absolute_video_url = f"{protocol}://{host}{video_url}"
                
                # Also create a direct download URL
                download_url = f"{protocol}://{host}/api/video/download/{filename}/"
                
                return Response({
                    "success": True,
                    "video_url": absolute_video_url,
                    "download_url": download_url,
                    "direct_access_url": absolute_video_url,
                    "filename": filename,
                    "message": "Video generated successfully"
                }, status=status.HTTP_200_OK)
            else:
                return Response({
                    "success": False,
                    "error": "Failed to generate video or video file not found",
                    "video_url": None
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                
        except Exception as e:
            return Response({
                "success": False,
                "error": f"An error occurred: {str(e)}",
                "video_url": None
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class VideoDownloadView(View):
    """
    View to handle direct video file downloads with proper headers
    """
    def get(self, request, filename):
        # Construct the file path
        file_path = os.path.join(settings.MEDIA_ROOT, filename)
        
        # Check if file exists
        if not os.path.exists(file_path):
            raise Http404("Video file not found")
        
        # Get the content type
        content_type, _ = mimetypes.guess_type(file_path)
        if content_type is None:
            content_type = 'application/octet-stream'
        
        # Create response with proper headers for download
        response = FileResponse(
            open(file_path, 'rb'),
            content_type=content_type
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        response['Content-Length'] = os.path.getsize(file_path)
        
        return response
