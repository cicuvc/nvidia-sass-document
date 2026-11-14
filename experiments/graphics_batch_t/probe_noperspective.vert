#version 450

layout(location = 0) noperspective out vec4 vcolor;

void main()
{
    vec2 positions[3] = vec2[](
        vec2(-1.0, -1.0),
        vec2( 3.0, -1.0),
        vec2(-1.0,  3.0)
    );
    gl_Position = vec4(positions[gl_VertexIndex], 0.0, 1.0);
    vcolor = vec4(float(gl_VertexIndex + 1u), 0.25, 0.5, 1.0);
}
