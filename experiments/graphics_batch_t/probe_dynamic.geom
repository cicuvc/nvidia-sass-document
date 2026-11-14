#version 450

layout(triangles) in;
layout(points, max_vertices = 1) out;

layout(location = 0) in vec4 vcolor[];
layout(location = 0) out vec4 gcolor;

void main()
{
    int index = int(gl_PrimitiveIDIn) & 1;
    gl_Position = gl_in[index].gl_Position;
    gcolor = vcolor[index];
    EmitVertex();
    EndPrimitive();
}
