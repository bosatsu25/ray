/*
 * dh_terrain: Distant Horizons の遠景の地形を G バッファへ書く (surface モジュール)
 * バニラの地形より先に描かれ、深度は DH の深度 (dhDepthTex) にだけ入る。照明は deferred30 が DH の深度から位置を戻して行う
 * テクスチャが無いので、アルベドは頂点色、法線は面の法線、材質は dhMaterialId から決める
 */
//@include "/lib/common/common.glsl"
//@include "/lib/common/dh.glsl"
//@include "/lib/common/color.glsl"
//@include "/lib/common/gbuffer.glsl"
//@include "/lib/ids/material_ids.glsl"
//@include "/lib/surface/material.glsl"
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
#include "/lib/ids/material_ids.glsl"
#include "/lib/ids/block_ids.glsl"
#include "/lib/surface/material.glsl"
// END GENERATED includes

in vec4 glcolor;
in vec3 normalPlayer;
in vec2 lmcoord;
in vec3 viewPos;
flat in int dhMaterial;

/* RENDERTARGETS: 1,2,3,15 */
layout(location = 0) out vec4 outAlbedo;
layout(location = 1) out vec4 outNormal;
layout(location = 2) out vec4 outMaterial;
layout(location = 3) out vec4 outVelocity;

// 溶岩と光るブロックの発光の強さ (G バッファの emission)。遠景は面が小さいので、光源ブロックの明るい画素と同じ 1 にする
const float DH_EMISSION = 1.0;

void main() {
#ifdef USE_DH
    vec3 playerPos = viewToPlayer(viewPos);
    // バニラの地形が必ずある範囲の内側は描かない。その外側で重なる所は、後から描かれるバニラの地形が上書きする
    if (length(playerPos.xz) < dhNearCutDistance()) discard;

    GBufferData g = gbufferDefault();
    g.albedo = srgbToLinear(glcolor.rgb);
    g.materialId = dhMaterial == DH_BLOCK_LEAVES ? MAT_LEAVES : dhMaterial == DH_BLOCK_SNOW ? MAT_SNOW : MAT_TERRAIN;
    g.geoNormal = normalize(normalPlayer);
    g.normal = g.geoNormal;
    g.lightmap = lmcoord;
    g.emission = (dhMaterial == DH_BLOCK_LAVA || dhMaterial == DH_BLOCK_ILLUMINATED) ? DH_EMISSION : 0.0;
    encodeGBuffer(g, outAlbedo, outNormal, outMaterial);
    outMaterial.a = encodeSurfaceExtra(1.0, 0.0);
    // 動かない面。a = 0 で、TAA は深度からの再投影 (バニラの深度は空なので、カメラの回転だけ) に任せる
    outVelocity = vec4(0.0);
#else
    discard;
#endif
}
