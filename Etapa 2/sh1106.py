from machine import Pin, I2C
import framebuf

class SH1106_I2C(framebuf.FrameBuffer):
    def __init__(self, width, height, i2c, addr=0x3C, external_vcc=False):
        self.width = width
        self.height = height
        self.i2c = i2c
        self.addr = addr
        self.external_vcc = external_vcc
        self.pages = self.height // 8
        self.buffer = bytearray(self.pages * self.width)
        super().__init__(self.buffer, self.width, self.height, framebuf.MONO_VLSB)
        self.init_display()

    def write_cmd(self, cmd):
        self.i2c.writeto(self.addr, bytearray([0x00, cmd]))

    def write_data(self, buf):
        self.i2c.writeto(self.addr, b'\x40' + buf)

    def init_display(self):
        for cmd in (
            0xAE,  # display off
            0xA8, self.height - 1,
            0xD3, 0x00,
            0x40,  # start line
            0xA1,  # segment remap
            0xC8,  # COM scan direction
            0xDA, 0x12,
            0x81, 0xCF,
            0xD9, 0xF1,
            0xDB, 0x40,
            0xA4,  # display follows RAM
            0xA6,  # normal display
            0xAF,  # display on
        ):
            self.write_cmd(cmd)
        self.fill(0)
        self.show()

    def show(self):
        for page in range(0, self.pages):
            self.write_cmd(0xB0 + page)
            self.write_cmd(0x02)      # lower column start (shift)
            self.write_cmd(0x10)      # higher column start
            start = self.width * page
            end = start + self.width
            self.write_data(self.buffer[start:end])
