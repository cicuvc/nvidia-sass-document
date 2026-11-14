#version 450

#extension GL_EXT_nonuniform_qualifier : require

layout(set = 0, binding = 0) uniform sampler2D textures[8];
layout(location = 0) out vec4 out_color;

void main()
{
    uint index = uint(gl_FragCoord.x) & 7u;
    vec2 uv = gl_FragCoord.xy / vec2(64.0);
    out_color = texture(textures[nonuniformEXT(index)], uv);
}
