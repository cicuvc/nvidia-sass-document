#version 450

layout(triangles) in;
layout(triangle_strip, max_vertices = 3) out;

layout(location = 0) in vec4 vcolor[];
layout(location = 0) out vec4 gcolor;

void main()
{
    for (int i = 0; i < 3; ++i) {
        gl_Position = gl_in[i].gl_Position;
        gcolor = vcolor[i];
        EmitVertex();
    }
    EndPrimitive();
}
