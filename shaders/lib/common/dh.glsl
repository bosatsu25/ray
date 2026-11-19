/*
 * Distant Horizons (DH) の遠景の地形を扱うための宣言と座標変換
 * Iris は DH の地形をバニラの地形より先に同じ colortex へ描くが、深度は別のテクスチャ (dhDepthTex0 / 1) に、別の投影
 * (dhProjection。near / far がバニラと違う) で書く。バニラの深度 (depthtex) には入らないので、DH の地形だけがある画素は
 * depthtex では空 (1.0) に見える。そういう画素を空と分けて扱う所で、ここの関数で位置を戻す
 * 実機では確かめていない (docs/architecture.md「既知の制約と未決事項」)
 */
#ifndef COMMON_DH_GLSL
#define COMMON_DH_GLSL

//@include "/lib/settings/capabilities.glsl"
//@include "/lib/common/dimension.glsl"
//@include "/lib/common/transforms.glsl"
//@include "/lib/common/uniforms.glsl"

// 空と大気のあるディメンションだけ (フォグの式が大気を前提にしている。ネザーとエンドは DH のプログラムごと止めてある)
#if defined FX_DISTANT_HORIZONS && defined HAS_SKY
#define USE_DH

uniform sampler2D dhDepthTex0; // DH の深度 (DH の水を含む)
uniform sampler2D dhDepthTex1; // DH の深度 (DH の水を含まない)
uniform mat4 dhProjectionInverse;
uniform int dhRenderDistance;  // DH の描画距離 (チャンク)

const float DH_CHUNK_BLOCKS = 16.0;
// バニラの地形が必ず描かれている範囲 (描画距離からこの分だけ内側) の DH の地形は捨てる。チャンクは四角く読まれ、
// カメラはチャンクの中のどこにでも居るので、描画距離の円からチャンク 2 個分を引く
const float DH_OVERLAP_BLOCKS = 32.0;
// 描画距離が短い時 (2 チャンクなど) に範囲が 0 以下にならないための下限 (描画距離に対する割合)
const float DH_OVERLAP_MIN = 0.5;

float dhRenderBlocks() { return float(dhRenderDistance) * DH_CHUNK_BLOCKS; }

vec3 dhScreenToView(vec3 screenPos) { return projectAndDivide(dhProjectionInverse, screenPos * 2.0 - 1.0); }
vec3 dhScreenToPlayer(vec3 screenPos) { return viewToPlayer(dhScreenToView(screenPos)); }

// DH の地形を捨てる水平の距離 (これより手前はバニラの地形が上から描く)
float dhNearCutDistance() { return max(far - DH_OVERLAP_BLOCKS, far * DH_OVERLAP_MIN); }
#endif

#endif
