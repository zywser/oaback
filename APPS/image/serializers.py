from  rest_framework import serializers
from django.core.validators import FileExtensionValidator




class UploadImageSerializer(serializers.Serializer):
    """
    ImageField： 会校验上传到文件是否是图片
    1. 网页标准格式（99% 业务必放）
    .jpg / .jpeg：JPG 照片
    .png：透明位图
    .gif：动图 / 静态图
    .webp：现代压缩图片
    """
    image = serializers.ImageField(
        validators = [FileExtensionValidator(["png","jpg","jpeg","gif","webp"])],
        error_messages = {"required": "请上传图片！","invalid_image": "请上传正确格式的图片！"}
    )
    """验证图片大小"""
    def validate_image(self, value):
        """图片大小单位是 “字节”
        1024B=1KB
        1024KB=1MB
        """
        max_size = 2 * 1024 * 1024
        size = value.size
        if size > max_size:
            raise serializers.ValidationError("图片不能超过2MB！")
        return  value