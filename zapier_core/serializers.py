from django.conf import settings
from rest_framework import serializers

from rest_hooks.models import Hook
from product_alerts.models import ProductChange
from leadgalaxy.models import ShopifyProduct, ShopifyStore, ShopifyOrderTrack
from shopify_orders.models import ShopifyOrder
from commercehq_core.models import CommerceHQProduct, CommerceHQStore, CommerceHQOrderTrack

from .payload import get_shopify_order_data


class HookSerializer(serializers.ModelSerializer):
    class Meta:
        model = Hook
        fields = ('id', 'event', 'target')

    def validate_event(self, event):
        if event not in settings.HOOK_EVENTS:
            err_msg = "Unexpected event {}".format(event)
            raise serializers.ValidationError(err_msg)
        return event

    def validate(self, data):
        event = data.get('event', self.instance.event if self.instance else None)
        target = data.get('target', self.instance.target if self.instance else None)
        try:
            obj = Hook.objects.get(event=event, target=target)
        except Hook.DoesNotExist:
            return data
        if self.instance and obj.id == self.instance.id:
            return data
        else:
            raise serializers.ValidationError("target {} exists for event {}".format(target, event))


# This serializer is used to send product alerts on fallback api endpoint
# Returned data should have same structure as the data sent to hooks
# product_alerts.models.ProductChange.send_hook_event_alert
class ProductAlertSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductChange
        fields = ('store_type',)

    def to_representation(self, obj):
        ret = super(ProductAlertSerializer, self).to_representation(obj)

        category = self.context.get('category')
        ret.update(obj.to_alert(category))
        return ret


# This serializer is used to send product changes on fallback api endpoint
# Returned data should have same structure as the data sent to hooks
# product_alerts.models.ProductChange.send_hook_event
class ProductChangeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductChange
        fields = ('store_type',)

    def to_representation(self, obj):
        ret = super(ProductChangeSerializer, self).to_representation(obj)

        category = self.context.get('category')
        change_index = self.context.get('change_index')
        ret.update(obj.to_dict({}, category, change_index))
        return ret


class ShopifyProductSerializer(serializers.ModelSerializer):
    store_type = serializers.SerializerMethodField()
    store_id = serializers.SerializerMethodField()

    class Meta:
        model = ShopifyProduct
        fields = ('id', 'title', 'store_type', 'store_id')

    def get_store_type(self, instance):
        return 'shopify'

    def get_store_id(self, instance):
        return instance.store.id

    def from_native(self, data, files=None):
        instance = super(serializers.ModelSerializer, self).from_native(data, files)
        if data.get('title', None):
            instance.update_data({'title': data.get('title', None)})
        if not self._errors:
            return self.full_clean(instance)


class CommerceHQProductSerializer(serializers.ModelSerializer):
    store_type = serializers.SerializerMethodField()
    store_id = serializers.SerializerMethodField()

    class Meta:
        model = CommerceHQProduct
        fields = ('id', 'title', 'store_type', 'store_id')

    def get_store_type(self, instance):
        return 'chq'

    def get_store_id(self, instance):
        return instance.store.id

    def from_native(self, data, files=None):
        instance = super(serializers.ModelSerializer, self).from_native(data, files)
        if data.get('title', None):
            instance.update_data({'title': data.get('title', None)})
        if not self._errors:
            return self.full_clean(instance)


class ShopifyStoreSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShopifyStore
        fields = ('id', 'title')


class CommerceHQStoreSerializer(serializers.ModelSerializer):
    class Meta:
        model = CommerceHQStore
        fields = ('id', 'title')


class ShopifyOrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShopifyOrder
        fields = ('total_price',)

    def to_representation(self, obj):
        ret = super(ShopifyOrderSerializer, self).to_representation(obj)
        data = self.context.get('data').get(str(obj.order_id), {})
        ret.update(get_shopify_order_data(obj.store, data))
        return ret


class ShopifyOrderTrackSerializer(serializers.ModelSerializer):
    store_type = serializers.SerializerMethodField()
    store_id = serializers.SerializerMethodField()
    store_title = serializers.SerializerMethodField()
    order_no = serializers.SerializerMethodField()
    source_status_label = serializers.SerializerMethodField()
    source_url = serializers.SerializerMethodField()

    class Meta:
        model = ShopifyOrderTrack
        fields = (
            'store_type',
            'store_id',
            'store_title',
            'order_no',
            'line_id',
            'source_id',
            'source_status',
            'source_status_label',
            'source_tracking',
            'source_status_details',
            'source_url',
        )

    def get_store_type(self, instance):
        return 'shopify'

    def get_store_id(self, instance):
        return instance.store.id

    def get_store_title(self, instance):
        return instance.store.title

    def get_order_no(self, instance):
        return instance.order_id

    def get_source_status_label(self, instance):
        return instance.get_source_status()

    def get_source_url(self, instance):
        return instance.get_source_url()


class CommerceHQOrderTrackSerializer(serializers.ModelSerializer):
    store_type = serializers.SerializerMethodField()
    store_id = serializers.SerializerMethodField()
    store_title = serializers.SerializerMethodField()
    order_no = serializers.SerializerMethodField()
    source_status_label = serializers.SerializerMethodField()
    source_url = serializers.SerializerMethodField()

    class Meta:
        model = CommerceHQOrderTrack
        fields = (
            'store_type',
            'store_id',
            'store_title',
            'order_no',
            'line_id',
            'source_id',
            'source_status',
            'source_status_label',
            'source_tracking',
            'source_status_details',
            'source_url',
        )

    def get_store_type(self, instance):
        return 'chq'

    def get_store_id(self, instance):
        return instance.store.id

    def get_store_title(self, instance):
        return instance.store.title

    def get_order_no(self, instance):
        return instance.order_id

    def get_source_status_label(self, instance):
        return instance.get_source_status()

    def get_source_url(self, instance):
        return instance.get_source_url()
