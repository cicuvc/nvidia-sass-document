#version 450

layout(triangles, equal_spacing, ccw) in;

layout(location = 0) in vec4 tcolor[];
layout(location = 0) out vec4 vcolor;

void main()
{
    vec3 weights = gl_TessCoord.xyz;
    gl_Position = weights.x * gl_in[0].gl_Position +
                  weights.y * gl_in[1].gl_Position +
                  weights.z * gl_in[2].gl_Position;
    vcolor = weights.x * tcolor[0] +
             weights.y * tcolor[1] +
             weights.z * tcolor[2];
}
