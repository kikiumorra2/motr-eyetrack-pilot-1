// Vue CLI / webpack configuration.
// - csv-loader lets us `import rows from "../materials/items.csv"` and get an array of objects.
// - publicPath is set so the built site works when served from a GitHub Pages sub-path
//   (https://<user>.github.io/<REPO_NAME>/); the deploy workflow sets REPO_NAME.
module.exports = {
  configureWebpack: {
    module: {
      rules: [
        {
          test: /\.(csv|tsv)$/,
          loader: "csv-loader",
          options: {
            dynamicTyping: true,
            header: true,
            skipEmptyLines: true,
          },
        },
      ],
    },
  },
  lintOnSave: false,
  pluginOptions: {
    lintStyleOnBuild: false,
    stylelint: {},
  },
  publicPath:
    process.env.NODE_ENV === "production" && process.env.REPO_NAME
      ? "/" + process.env.REPO_NAME + "/"
      : "/",
};
