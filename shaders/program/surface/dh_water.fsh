/*
 * dh_water: Distant Horizons の遠景の水 (surface モジュール)
 * 不透明の照明 (deferred) の後、バニラの水より先に描かれる。バニラの水の経路 (colortex4 / 5 に書いて composite で屈折と反射を足す) は
 * バニラの深度を前提にしていて DH の水には使えないので、ここで照らして colortex0 に不透明で書く
 * 遠景の水はかすめ角で見るので、ほとんどが空の映り込みになる。水の体の色は頂点色 (バイオームの水の色) を空と太陽で照らした拡散
 */
//@include "/lib/common/common.glsl"
//@include "/lib/common/dh.glsl"
//@include "/lib/common/color.glsl"
//@include "/lib/surface/surface.glsl"
//@include "/lib/sky/sky.glsl"
//@include "/lib/light/light.glsl"
//@include "/lib/surface/surface_lights.glsl"
//@include "/lib/surface/water_shading.glsl"
// BEGIN GENERATED includes (tools/gen_includes.py)
#include "/lib/settings/look.glsl"
#include "/lib/settings/light.glsl"
#include "/lib/settings/surface.glsl"
#include "/lib/settings/sky.glsl"
#include "/lib/settings/post.glsl"
#include "/lib/settings/internal.glsl"
#include "/lib/settings/bool_refs.glsl"
#include "/lib/settings.glsl"
#include "/lib/common/dimension.glsl"
#include "/lib/common/constants.glsl"
#include "/lib/common/uniforms.glsl"
#include "/lib/common/samplers.glsl"
#include "/lib/common/math.glsl"
#include "/lib/common/shading_types.glsl"
#include "/lib/common/common.glsl"
#include "/lib/settings/capabilities.glsl"
#include "/lib/common/transforms.glsl"
#include "/lib/common/dh.glsl"
#include "/lib/common/color.glsl"
#include "/lib/common/encoding.glsl"
#include "/lib/common/gbuffer.glsl"
#include "/lib/ids/block_ids.glsl"
#include "/lib/ids/material_ids.glsl"
#include "/lib/surface/material.glsl"
#include "/lib/surface/brdf.glsl"
#include "/lib/common/frame_offset.glsl"
#include "/lib/common/look_presets.glsl"
#include "/lib/common/voxel_space.glsl"
#include "/lib/buffers/images.glsl"
#include "/lib/buffers/slots.glsl"
#include "/lib/surface/gi.glsl"
#include "/lib/common/noise.glsl"
#include "/lib/buffers/frame_data.glsl"
#include "/lib/common/water_waves.glsl"
#include "/lib/common/water_glitter.glsl"
#include "/lib/common/water_lod.glsl"
#include "/lib/common/water_normal.glsl"
#include "/lib/common/water.glsl"
#include "/lib/common/shadow_space.glsl"
#include "/lib/common/shadow_volume.glsl"
#include "/lib/surface/sun_shadow.glsl"
#include "/lib/ids/light_ids.glsl"
#include "/lib/surface/waving.glsl"
#include "/lib/surface/surface.glsl"
#include "/lib/sky/sh.glsl"
#include "/lib/common/phase.glsl"
#include "/lib/sky/atmosphere.glsl"
#include "/lib/common/celestial_shape.glsl"
#include "/lib/sky/celestial.glsl"
#include "/lib/sky/cloud_styles.glsl"
#include "/lib/sky/clouds.glsl"
#include "/lib/sky/sky_color.glsl"
#include "/lib/sky/fog_template.glsl"
#include "/lib/sky/climate.glsl"
#include "/lib/sky/fog_styles.glsl"
#include "/lib/sky/fog.glsl"
#include "/lib/sky/sky.glsl"
#include "/lib/buffers/light_bins.glsl"
#include "/lib/light/light_bins.glsl"
#include "/lib/buffers/block_data.glsl"
#include "/lib/light/light_def.glsl"
#include "/lib/light/light_table_data.glsl"
#include "/lib/light/light_table.glsl"
#include "/lib/light/block_data.glsl"
#include "/lib/ids/entity_ids.glsl"
#include "/lib/ids/id_decode.glsl"
#include "/lib/light/voxel_read.glsl"
#include "/lib/light/voxel.glsl"
#include "/lib/light/floodfill.glsl"
#include "/lib/buffers/entity_tris.glsl"
#include "/lib/light/entity_tri.glsl"
#include "/lib/light/trace.glsl"
#include "/lib/buffers/global_lights.glsl"
#include "/lib/light/light_select.glsl"
#include "/lib/light/hand_pose.glsl"
#include "/lib/light/entity_light.glsl"
#include "/lib/light/hand_light.glsl"
#include "/lib/light/blocklight.glsl"
#include "/lib/light/light.glsl"
#include "/lib/surface/surface_lights.glsl"
#include "/lib/common/exposure.glsl"
#include "/lib/common/joint_bilateral.glsl"
#include "/lib/surface/lighting.glsl"
#include "/lib/surface/screen_trace.glsl"
#include "/lib/surface/reflection.glsl"
#include "/lib/surface/composite_specular.glsl"
#include "/lib/surface/water_shading.glsl"
// END GENERATED includes

in vec4 glcolor;
in vec3 normalPlayer;
in vec2 lmcoord;
in vec3 viewPos;
flat in int dhMaterial;

/* RENDERTARGETS: 0 */
layout(location = 0) out vec4 outColor;

// 水の体の色の濃さ (頂点色に掛ける拡散反射率)。水は入った光のほとんどを吸うので暗い
const float DH_WATER_BODY_ALBEDO = 0.08;
// 映り込みを読む向きの上向きの下限 (水平線より下を向くと虚空の色を読む)
const float DH_WATER_REFLECT_MIN_Y = 0.02;

void main() {
#ifdef USE_DH
    ivec2 texel = ivec2(gl_FragCoord.xy);
    vec3 playerPos = viewToPlayer(viewPos);
    // バニラの地形が手前にある画素と、バニラの地形が必ずある範囲の内側は描かない (DH の深度はバニラの地形を知らない)
    if (length(playerPos.xz) < dhNearCutDistance() || texelFetch(depthtex0, texel, 0).r < 1.0) discard;

    vec3 N = normalize(normalPlayer);
    vec3 V = -normalize(playerPos);
    SurfacePoint sp = surfacePoint(playerPos, N);
    sp.lightmap = lmcoord;
    // 影マップの距離の外なので、太陽は影なし (雲影とスカイライトの絞りだけ)
    SurfaceLights L = gatherSurfaceLights(sp, SL_SUN_NONE, SL_BLOCK_NONE, SL_SKY | SL_CELESTIAL);
    vec3 sunE = L.celestial.irradiance * (saturate(dot(N, L.celestial.direction)) * getCloudShadow(playerPos) * sunSkylightGate(lmcoord.y));
    vec3 body = srgbToLinear(glcolor.rgb) * (DH_WATER_BODY_ALBEDO * RCP_PI) * (L.sky + sunE);

    float NoV = saturate(dot(N, V));
    float fresnel = WATER_F0 + (1.0 - WATER_F0) * pow(1.0 - NoV, 5.0);
    vec3 reflectDir = reflect(-V, N);
    reflectDir.y = max(reflectDir.y, DH_WATER_REFLECT_MIN_Y);
    vec3 reflection = getSkyRadiance(normalize(reflectDir)) * skylightCurve(lmcoord.y);

    // a = 1 は鏡面の白飛び分なし (lib/common/specular_sparkle.glsl の約束)
    outColor = vec4(mix(body, reflection, fresnel), 1.0);
#else
    discard;
#endif
}
