'use strict';

module.exports = {
  ...require('./renderer'),
  ...require('./accessibility'),
  ...require('./computedStyle'),
  ...require('./visualRegression'),
  ...require('./report'),
  ...require('./validator'),
};
