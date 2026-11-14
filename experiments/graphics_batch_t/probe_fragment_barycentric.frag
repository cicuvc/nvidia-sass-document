#version 450

#extension GL_EXT_fragment_shader_barycentric : require

layout(location = 0) pervertexEXT in vec4 colors[3];
layout(location = 0) out vec4 out_color;

void main()
{
    vec3 bary = gl_BaryCoordEXT;
    out_color = bary.x * colors[0] +
                bary.y * colors[1] +
                bary.z * colors[2];
}
