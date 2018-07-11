from django.conf import settings
from rest_framework import serializers

from rest_hooks.models import Hook
from product_alerts.models import ProductChange
from leadgalaxy.models import ShopifyProduct, ShopifyStore
from shopify_orders.models import ShopifyOrder
from commercehq_core.models import CommerceHQProduct, CommerceHQStore


class HookSerializer(serializers.ModelSerializer):
    class Meta:
        model = Hook
        fields = ('id', 'event', 'target')

    def validate_event(self, attrs, source):
        event = attrs[source]
        if event not in settings.HOOK_EVENTS:
            err_msg = "Unexpected event {}".format(event)
            raise serializers.ValidationError(message=err_msg, code=400)
        return attrs

    def validate(self, attrs):
        event = attrs.get('event', self.object.event if self.object else None)
        target = attrs.get('target', self.object.target if self.object else None)
        try:
            obj = Hook.objects.get(event=event, target=target)
        except Hook.DoesNotExist:
            return attrs
        if self.object and obj.id == self.object.id:
            return attrs
        else:
            raise serializers.ValidationError("target {} exists for event {}".format(target, event))


# This serializer is used to send product changes on fallback api endpoint
# Returned data should have same structure as the data sent to hooks
# product_alerts.models.ProductChange.send_hook_event
class ProductChangeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductChange
        fields = ('store_type',)

    def to_native(self, obj):
        ret = super(ProductChangeSerializer, self).to_native(obj)

        category = self.context.get('category')
        change_index = self.context.get('change_index')
        ret.update(obj.to_dict({}, category, change_index))
        return ret


class ShopifyProductSerializer(serializers.ModelSerializer):
    store_type = serializers.SerializerMethodField('get_store_type')
    store_id = serializers.SerializerMethodField('get_store_id')

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
    store_type = serializers.SerializerMethodField('get_store_type')
    store_id = serializers.SerializerMethodField('get_store_id')

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
        fields = ('order_id',)

    def to_native(self, obj):
        ret = super(ShopifyOrderSerializer, self).to_native(obj)
        ret.update(obj.to_dict())
        return ret
