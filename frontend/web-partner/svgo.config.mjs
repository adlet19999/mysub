const config = {
  multipass: true,
  js2svg: {
    indent: 2,
    pretty: false,
  },
  plugins: [
    "preset-default",
    {
      name: "removeViewBox",
      active: false,
    },
    {
      name: "sortAttrs",
      params: {
        xmlnsOrder: "front",
      },
    },
  ],
};

export default config;
