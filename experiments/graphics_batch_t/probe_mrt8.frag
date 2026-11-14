#version 450

layout(location = 0) out vec4 color0;
layout(location = 1) out vec4 color1;
layout(location = 2) out vec4 color2;
layout(location = 3) out vec4 color3;
layout(location = 4) out vec4 color4;
layout(location = 5) out vec4 color5;
layout(location = 6) out vec4 color6;
layout(location = 7) out vec4 color7;

void main()
{
    color0 = vec4(0.125, 0.250, 0.375, 1.0);
    color1 = vec4(1.000, 0.875, 0.750, 1.0);
    color2 = vec4(0.250, 0.500, 0.750, 1.0);
    color3 = vec4(0.750, 0.500, 0.250, 1.0);
    color4 = vec4(0.200, 0.400, 0.600, 1.0);
    color5 = vec4(0.600, 0.400, 0.200, 1.0);
    color6 = vec4(0.300, 0.600, 0.900, 1.0);
    color7 = vec4(0.900, 0.600, 0.300, 1.0);
}
