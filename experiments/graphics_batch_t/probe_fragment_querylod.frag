#version 450

layout(set = 0, binding = 0) uniform sampler2D input_texture;
layout(location = 0) out vec4 out_color;

void main()
{
    vec2 uv = gl_FragCoord.xy / vec2(64.0);
    vec2 lod = textureQueryLod(input_texture, uv);
    out_color = vec4(lod, 0.0, 1.0);
}
