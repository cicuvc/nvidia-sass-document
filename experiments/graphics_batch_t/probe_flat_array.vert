#version 450

layout(location = 0) flat out vec4 varyings[4];

void main()
{
    vec2 positions[3] = vec2[](
        vec2(-1.0, -1.0),
        vec2( 3.0, -1.0),
        vec2(-1.0,  3.0)
    );
    gl_Position = vec4(positions[gl_VertexIndex], 0.0, 1.0);
    varyings[0] = vec4(1.0, 0.0, 0.0, 1.0);
    varyings[1] = vec4(0.0, 1.0, 0.0, 1.0);
    varyings[2] = vec4(0.0, 0.0, 1.0, 1.0);
    varyings[3] = vec4(1.0, 1.0, 0.0, 1.0);
}
