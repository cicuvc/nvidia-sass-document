#version 450

layout(location = 0) out vec4 color0;
layout(location = 1) out vec4 color1;

void main()
{
    gl_FragDepth = 0.25 + gl_FragCoord.x * (1.0 / 1024.0);
    color0 = vec4(1.0, 2.0, 3.0, 4.0);
    color1 = vec4(5.0, 6.0, 7.0, 8.0);
}
