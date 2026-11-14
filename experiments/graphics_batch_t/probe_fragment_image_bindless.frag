#version 450

#extension GL_EXT_nonuniform_qualifier : require

layout(set = 0, binding = 1, rgba8) uniform image2D storage_images[8];
layout(location = 0) out vec4 out_color;

void main()
{
    uint index = uint(gl_FragCoord.x) & 7u;
    ivec2 coord = ivec2(gl_FragCoord.xy);
    vec4 value = imageLoad(
        storage_images[nonuniformEXT(index)], coord);
    imageStore(
        storage_images[nonuniformEXT(index)], coord, value);
    out_color = value;
}
