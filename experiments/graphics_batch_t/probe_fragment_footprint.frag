#version 450

#extension GL_NV_shader_texture_footprint : require

layout(set = 0, binding = 0) uniform sampler2D input_texture;
layout(location = 0) out vec4 out_color;

void main()
{
    gl_TextureFootprint2DNV footprint;
    vec2 uv = gl_FragCoord.xy / vec2(64.0);
    bool valid = textureFootprintNV(
        input_texture, uv, 4, false, footprint);
    out_color = vec4(vec2(footprint.anchor),
                     float(footprint.lod),
                     valid ? 1.0 : 0.0);
}
