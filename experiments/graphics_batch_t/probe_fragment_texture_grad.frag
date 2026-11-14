#version 450

layout(set = 0, binding = 0) uniform sampler2D input_texture;
layout(location = 0) out vec4 out_color;

void main()
{
    vec2 uv = gl_FragCoord.xy / vec2(64.0);
    vec2 dx = dFdx(uv);
    vec2 dy = dFdy(uv);
    out_color = textureGrad(input_texture, uv, dx, dy);
}
