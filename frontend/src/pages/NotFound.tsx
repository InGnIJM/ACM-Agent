import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";

export default function NotFound() {
  return (
    <Box sx={{ p: 3, textAlign: "center", mt: 8 }}>
      <Typography variant="h3" color="text.secondary" gutterBottom>
        404
      </Typography>
      <Typography variant="h5" color="text.secondary">
        Page Not Found
      </Typography>
    </Box>
  );
}
