from scadwright.primitives import cylinder
# Bolt pattern: 5 cylinders along X axis.
MODEL = cylinder(h=10, r=2, fn=16).linear_copy([8, 0, 0], n=5)
