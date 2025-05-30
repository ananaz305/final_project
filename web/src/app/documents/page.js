import React from 'react';

import Box from "@mui/material/Box";
import { Menu } from "@/components/Menu/Menu";
import Typography from "@mui/material/Typography";

const Page = () => {
    return (
        <Box sx={{display: 'flex', width: '100%', height: '100%'}}>
            <Menu currentPage="documents" />
            <Box sx={{flexGrow: 1, position: 'relative', padding: 4}}>
                <Typography variant="h4">In development</Typography>
                <img alt="union jack"
                     src="https://upload.wikimedia.org/wikipedia/commons/thumb/a/a5/Flag_of_the_United_Kingdom_%281-2%29.svg/1200px-Flag_of_the_United_Kingdom_%281-2%29.svg.png"
                     style={{
                         position: 'absolute',
                         width: '100%',
                         inset: 0,
                         objectFit: 'cover',
                         objectPosition: 'center',
                         opacity: '0.3'
                     }}/>
            </Box>
        </Box>
    );
}

export default Page;
