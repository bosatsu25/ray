/*
 * dh_terrain / dh_water: Distant Horizons の遠景の地形と水の頂点シェーダー (surface モジュール)
 * DH の頂点が持つのは位置・頂点色 (ブロックの平均の色)・法線・ライトマップ・材質の種類 (dhMaterialId) だけで、テクスチャと mc_Entity は無い
 */
//@include "/lib/common/common.glsl"
//@include "/lib/common/dh.glsl"
//@include "/lib/common/jitter.glsl"
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
#include "/lib/common/jitter.glsl"
// END GENERATED includes

out vec4 glcolor;
out vec3 normalPlayer;
out vec2 lmcoord;
out vec3 viewPos;
flat out int dhMaterial;
// dh_water.fsh が取り込む surface の lib (composite_specular.glsl) が全画面パス用の texcoord を入力に宣言している
// DH の描画では使わないが、頂点側に出力が無いとリンクできないドライバがある (Mesa) ので出しておく
out vec2 texcoord;

// Iris は DH のライトマップを (レベル + 0.5) / 16 で渡す。gbuffers と同じ 0-1 (レベル / 15) に直す
const float DH_LIGHTMAP_TEXELS = 16.0;
const float DH_LIGHTMAP_RANGE = 15.0;

void main() {
    glcolor = gl_Color;
    lmcoord = saturate((gl_MultiTexCoord2.xy * DH_LIGHTMAP_TEXELS - 0.5) / DH_LIGHTMAP_RANGE);
    normalPlayer = viewToPlayerDir(normalize(gl_NormalMatrix * gl_Normal));
    viewPos = (gl_ModelViewMatrix * gl_Vertex).xyz;
    dhMaterial = dhMaterialId;
    texcoord = vec2(0.0);
    // gl_ProjectionMatrix は DH の投影 (near / far がバニラと違う)。ジッターはバニラの地形と同じだけ掛けて、TAA が同じ履歴で均せるようにする
    gl_Position = gl_ProjectionMatrix * vec4(viewPos, 1.0);
    applyTaaJitter(gl_Position);
}
