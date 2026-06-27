/**
 * Calibration API — /api/v1/calibration/*
 * Stub: pending full implementation.
 */
const express = require('express');
const router = express.Router();

router.get('*', (req, res) => {
  res.status(503).json({ status: 'unavailable', message: 'calibration API not yet implemented' });
});

module.exports = router;
