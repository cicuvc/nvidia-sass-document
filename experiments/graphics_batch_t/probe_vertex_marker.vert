#version 450

layout(location = 0) out vec4 vcolor;

void main()
{
    vec2 positions[3] = vec2[](
        vec2(-1.0, -1.0),
        vec2( 3.0, -1.0),
        vec2(-1.0,  3.0)
    );
    uint index = uint(gl_VertexIndex);
    uint marker = index * 0x01234567u ^ 0x76543210u;
    gl_Position = vec4(positions[gl_VertexIndex], 0.0, 1.0);
    vcolor = uintBitsToFloat(uvec4(marker,
                                   marker ^ 0xa5a5a5a5u,
                                   marker + 0x13579bdfu,
                                   index));
}
