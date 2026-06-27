/**
 * Personal Health API — /api/v1/personal-health/*
 * Stub: pending full implementation.
 */
const express = require('express');
const router = express.Router();

router.get('*', (req, res) => {
  res.status(503).json({ status: 'unavailable', message: 'personal-health API not yet implemented' });
});

module.exports = router;
