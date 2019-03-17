from django.views.generic import View
from django.core.exceptions import PermissionDenied

from shopified_core.mixins import ApiResponseMixin
from shopified_core.utils import safe_int

from .models import VideosList


class TubeHuntApi(ApiResponseMixin, View):
    def get_video_lists(self, request, user, data):
        lists = VideosList.objects.filter(user=user).values('id', 'title')
        lists = list(lists)

        return self.api_success({'lists': lists})

    def post_video_list(self, request, user, data):
        if not user.can('youtube_ads.use'):
            raise PermissionDenied()

        title = data.get('newListTitle', '').strip()
        list_id = safe_int(data.get('selectedList'))
        videos = data.get('selected').strip(';').split(';')

        if not title and not list_id:
            return self.api_error('Please select a list or create a new one.')

        if title:
            video_list = VideosList(title=title, user=user)
        else:
            try:
                video_list = VideosList.objects.get(user=user, pk=list_id)
            except VideosList.DoesNotExist:
                return self.api_error('Video list not found', status=404)

        video_list.add_videos(videos)
        video_list.save()

        return self.api_success({'id': video_list.pk})

    def delete_video_list(self, request, user, data):
        list_id = safe_int(data.get('list_id'))

        try:
            video_list = VideosList.objects.get(user=user, pk=list_id)
        except VideosList.DoesNotExist:
            return self.api_error('Video list not found', status=404)

        video_list.delete()

        return self.api_success()

    def delete_list_video(self, request, user, data):
        list_id = safe_int(data.get('list_id'))
        video_id = data.get('video_id')

        if not video_id:
            return self.api_error('Video ID is required.')

        if not isinstance(video_id, str):
            return self.api_error('Video ID is invalid.')

        try:
            video_list = VideosList.objects.get(user=user, pk=list_id)
        except VideosList.DoesNotExist:
            return self.api_error('Video list not found', status=404)

        try:
            video_list.remove_video(video_id)
        except ValueError:
            return self.api_error('Video ID not in list.')

        video_list.save()

        return self.api_success()

    def delete_list_videos(self, request, user, data):
        list_id = safe_int(data.get('list_id'))
        video_ids = data.getlist('video_ids[]')

        try:
            video_list = VideosList.objects.get(user=user, pk=list_id)
        except VideosList.DoesNotExist:
            return self.api_error('Video list not found', status=404)

        deleted = []
        for video_id in video_ids:
            try:
                video_list.remove_video(video_id)
            except ValueError:
                continue
            else:
                deleted.append(video_id)

        video_list.save()

        return self.api_success({'deleted': deleted})
