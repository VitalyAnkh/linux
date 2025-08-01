// SPDX-License-Identifier: MIT

#include <linux/export.h>
#include <linux/moduleparam.h>
#include <linux/vmalloc.h>

#include <drm/drm_crtc_helper.h>
#include <drm/drm_drv.h>
#include <drm/drm_fb_helper.h>
#include <drm/drm_framebuffer.h>
#include <drm/drm_gem.h>
#include <drm/drm_print.h>

#include <drm/drm_fbdev_ttm.h>

/* @user: 1=userspace, 0=fbcon */
static int drm_fbdev_ttm_fb_open(struct fb_info *info, int user)
{
	struct drm_fb_helper *fb_helper = info->par;

	/* No need to take a ref for fbcon because it unbinds on unregister */
	if (user && !try_module_get(fb_helper->dev->driver->fops->owner))
		return -ENODEV;

	return 0;
}

static int drm_fbdev_ttm_fb_release(struct fb_info *info, int user)
{
	struct drm_fb_helper *fb_helper = info->par;

	if (user)
		module_put(fb_helper->dev->driver->fops->owner);

	return 0;
}

FB_GEN_DEFAULT_DEFERRED_SYSMEM_OPS(drm_fbdev_ttm,
				   drm_fb_helper_damage_range,
				   drm_fb_helper_damage_area);

static void drm_fbdev_ttm_fb_destroy(struct fb_info *info)
{
	struct drm_fb_helper *fb_helper = info->par;
	void *shadow = info->screen_buffer;

	if (!fb_helper->dev)
		return;

	fb_deferred_io_cleanup(info);
	drm_fb_helper_fini(fb_helper);
	vfree(shadow);
	drm_client_framebuffer_delete(fb_helper->buffer);

	drm_client_release(&fb_helper->client);
	drm_fb_helper_unprepare(fb_helper);
	kfree(fb_helper);
}

static const struct fb_ops drm_fbdev_ttm_fb_ops = {
	.owner		= THIS_MODULE,
	.fb_open	= drm_fbdev_ttm_fb_open,
	.fb_release	= drm_fbdev_ttm_fb_release,
	FB_DEFAULT_DEFERRED_OPS(drm_fbdev_ttm),
	DRM_FB_HELPER_DEFAULT_OPS,
	.fb_destroy	= drm_fbdev_ttm_fb_destroy,
};

static void drm_fbdev_ttm_damage_blit_real(struct drm_fb_helper *fb_helper,
					   struct drm_clip_rect *clip,
					   struct iosys_map *dst)
{
	struct drm_framebuffer *fb = fb_helper->fb;
	size_t offset = clip->y1 * fb->pitches[0];
	size_t len = clip->x2 - clip->x1;
	unsigned int y;
	void *src;

	switch (drm_format_info_bpp(fb->format, 0)) {
	case 1:
		offset += clip->x1 / 8;
		len = DIV_ROUND_UP(len + clip->x1 % 8, 8);
		break;
	case 2:
		offset += clip->x1 / 4;
		len = DIV_ROUND_UP(len + clip->x1 % 4, 4);
		break;
	case 4:
		offset += clip->x1 / 2;
		len = DIV_ROUND_UP(len + clip->x1 % 2, 2);
		break;
	default:
		offset += clip->x1 * fb->format->cpp[0];
		len *= fb->format->cpp[0];
		break;
	}

	src = fb_helper->info->screen_buffer + offset;
	iosys_map_incr(dst, offset); /* go to first pixel within clip rect */

	for (y = clip->y1; y < clip->y2; y++) {
		iosys_map_memcpy_to(dst, 0, src, len);
		iosys_map_incr(dst, fb->pitches[0]);
		src += fb->pitches[0];
	}
}

static int drm_fbdev_ttm_damage_blit(struct drm_fb_helper *fb_helper,
				     struct drm_clip_rect *clip)
{
	struct drm_client_buffer *buffer = fb_helper->buffer;
	struct iosys_map map, dst;
	int ret;

	/*
	 * We have to pin the client buffer to its current location while
	 * flushing the shadow buffer. In the general case, concurrent
	 * modesetting operations could try to move the buffer and would
	 * fail. The modeset has to be serialized by acquiring the reservation
	 * object of the underlying BO here.
	 *
	 * For fbdev emulation, we only have to protect against fbdev modeset
	 * operations. Nothing else will involve the client buffer's BO. So it
	 * is sufficient to acquire struct drm_fb_helper.lock here.
	 */
	mutex_lock(&fb_helper->lock);

	ret = drm_client_buffer_vmap_local(buffer, &map);
	if (ret)
		goto out;

	dst = map;
	drm_fbdev_ttm_damage_blit_real(fb_helper, clip, &dst);

	drm_client_buffer_vunmap_local(buffer);

out:
	mutex_unlock(&fb_helper->lock);

	return ret;
}

static int drm_fbdev_ttm_helper_fb_dirty(struct drm_fb_helper *helper,
					 struct drm_clip_rect *clip)
{
	struct drm_device *dev = helper->dev;
	int ret;

	/* Call damage handlers only if necessary */
	if (!(clip->x1 < clip->x2 && clip->y1 < clip->y2))
		return 0;

	ret = drm_fbdev_ttm_damage_blit(helper, clip);
	if (drm_WARN_ONCE(dev, ret, "Damage blitter failed: ret=%d\n", ret))
		return ret;

	if (helper->fb->funcs->dirty) {
		ret = helper->fb->funcs->dirty(helper->fb, NULL, 0, 0, clip, 1);
		if (drm_WARN_ONCE(dev, ret, "Dirty helper failed: ret=%d\n", ret))
			return ret;
	}

	return 0;
}

static const struct drm_fb_helper_funcs drm_fbdev_ttm_helper_funcs = {
	.fb_dirty = drm_fbdev_ttm_helper_fb_dirty,
};

/*
 * struct drm_driver
 */

int drm_fbdev_ttm_driver_fbdev_probe(struct drm_fb_helper *fb_helper,
				     struct drm_fb_helper_surface_size *sizes)
{
	struct drm_client_dev *client = &fb_helper->client;
	struct drm_device *dev = fb_helper->dev;
	struct drm_client_buffer *buffer;
	struct fb_info *info;
	size_t screen_size;
	void *screen_buffer;
	u32 format;
	int ret;

	drm_dbg_kms(dev, "surface width(%d), height(%d) and bpp(%d)\n",
		    sizes->surface_width, sizes->surface_height,
		    sizes->surface_bpp);

	format = drm_driver_legacy_fb_format(dev, sizes->surface_bpp,
					     sizes->surface_depth);
	buffer = drm_client_framebuffer_create(client, sizes->surface_width,
					       sizes->surface_height, format);
	if (IS_ERR(buffer))
		return PTR_ERR(buffer);

	fb_helper->funcs = &drm_fbdev_ttm_helper_funcs;
	fb_helper->buffer = buffer;
	fb_helper->fb = buffer->fb;

	screen_size = buffer->gem->size;
	screen_buffer = vzalloc(screen_size);
	if (!screen_buffer) {
		ret = -ENOMEM;
		goto err_drm_client_framebuffer_delete;
	}

	info = drm_fb_helper_alloc_info(fb_helper);
	if (IS_ERR(info)) {
		ret = PTR_ERR(info);
		goto err_vfree;
	}

	drm_fb_helper_fill_info(info, fb_helper, sizes);

	info->fbops = &drm_fbdev_ttm_fb_ops;

	/* screen */
	info->flags |= FBINFO_VIRTFB | FBINFO_READS_FAST;
	info->screen_buffer = screen_buffer;
	info->fix.smem_len = screen_size;

	/* deferred I/O */
	fb_helper->fbdefio.delay = HZ / 20;
	fb_helper->fbdefio.deferred_io = drm_fb_helper_deferred_io;

	info->fbdefio = &fb_helper->fbdefio;
	ret = fb_deferred_io_init(info);
	if (ret)
		goto err_drm_fb_helper_release_info;

	return 0;

err_drm_fb_helper_release_info:
	drm_fb_helper_release_info(fb_helper);
err_vfree:
	vfree(screen_buffer);
err_drm_client_framebuffer_delete:
	fb_helper->fb = NULL;
	fb_helper->buffer = NULL;
	drm_client_framebuffer_delete(buffer);
	return ret;
}
EXPORT_SYMBOL(drm_fbdev_ttm_driver_fbdev_probe);
