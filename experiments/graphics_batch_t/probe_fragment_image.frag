#version 450

layout(set = 0, binding = 1, rgba8) uniform image2D storage_image;
layout(location = 0) out vec4 out_color;

void main()
{
    ivec2 coord = ivec2(gl_FragCoord.xy);
    vec4 value = imageLoad(storage_image, coord);
    imageStore(storage_image, coord, value + vec4(0.25));
    out_color = value;
}
