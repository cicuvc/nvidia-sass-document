#version 450

layout(location = 0) flat in vec4 varyings[4];
layout(location = 0) out vec4 out_color;

void main()
{
    uint index = uint(gl_PrimitiveID) & 3u;
    out_color = varyings[index];
}
