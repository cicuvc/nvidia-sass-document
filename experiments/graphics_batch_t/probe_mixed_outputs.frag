#version 450

layout(location = 0) out vec4 color0;
layout(location = 1) out vec2 color1;
layout(location = 2) out float color2;
layout(location = 3) out vec4 color3;
layout(location = 4) out vec2 color4;
layout(location = 5) out float color5;
layout(location = 6) out vec4 color6;
layout(location = 7) out vec2 color7;

void main()
{
    color0 = vec4(1.0, 2.0, 3.0, 4.0);
    color1 = vec2(5.0, 6.0);
    color2 = 7.0;
    color3 = vec4(8.0, 9.0, 10.0, 11.0);
    color4 = vec2(12.0, 13.0);
    color5 = 14.0;
    color6 = vec4(15.0, 16.0, 17.0, 18.0);
    color7 = vec2(19.0, 20.0);
}
