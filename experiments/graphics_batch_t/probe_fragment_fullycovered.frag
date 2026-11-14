#version 450

#extension GL_NV_conservative_raster_underestimation : require

layout(location = 0) out vec4 out_color;

void main()
{
    out_color = vec4(gl_FragFullyCoveredNV ? 1.0 : 0.0);
}
