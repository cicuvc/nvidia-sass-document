#version 450

layout(vertices = 3) out;

layout(location = 0) in vec4 vcolor[];
layout(location = 0) out vec4 tcolor[];

void main()
{
    gl_out[gl_InvocationID].gl_Position =
        gl_in[gl_InvocationID].gl_Position;
    tcolor[gl_InvocationID] = vcolor[gl_InvocationID];
    if (gl_InvocationID == 0) {
        gl_TessLevelOuter[0] = 1.0;
        gl_TessLevelOuter[1] = 1.0;
        gl_TessLevelOuter[2] = 1.0;
        gl_TessLevelInner[0] = 1.0;
    }
}
