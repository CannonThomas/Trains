from cffi import FFI

ffibuilder = FFI()

ffibuilder.cdef("""
    int initialize(void);
    int terminate(void);

    void forward(int n);
    void backward(int n);
    void stop(int n);
    void idle(int n);
    void function(int n, int type);
""")

ffibuilder.set_source(
    "pkt_send",
    """
    #include "packet_sender.h"
    """,
    sources=["packet_sender.c"],
    include_dirs=[
        ".",
        "/usr/local/include/piolib",
    ],
    library_dirs=[
        "/usr/local/lib",
    ],
    libraries=[
        "pio",
        "lgpio",
    ],
    extra_compile_args=[
        "-O2",
    ],
    extra_link_args=[
        "-Wl,-rpath,/usr/local/lib",
    ],
)

if __name__ == "__main__":
    ffibuilder.compile(verbose=True)