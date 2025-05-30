'use client'

import React, {useState} from 'react';

import AppBar from '@mui/material/AppBar';
import Box from '@mui/material/Box';
import Toolbar from '@mui/material/Toolbar';
import Typography from '@mui/material/Typography';
import Container from '@mui/material/Container';

import { LoginForm } from "@/components/LoginForm/LoginForm";
import {useLoginContext} from "@/providers";

export const Header = () => {
    const { user, setUser } = useLoginContext();

    const [isOpen, setOpen] = useState(false);

    const handleClose = () => setOpen(false);

    return (
        <>
            <AppBar position="relative">
                <Container maxWidth="xl">
                    <Toolbar disableGutters>
                        <Box sx={{ flexGrow: 1 }}>
                            {user && (
                                <Typography
                                    variant="h6"
                                    noWrap
                                    sx={{
                                        mr: 2,
                                        fontFamily: 'monospace',
                                        fontWeight: 700,
                                        color: 'inherit',
                                        textDecoration: 'none',
                                    }}
                                >
                                    Good afternoon, {user.firstName}&nbsp;{user.lastName}
                                </Typography>
                            )}
                        </Box>
                        <Box sx={{ flexGrow: 0 }}>
                            <Typography
                                variant="h6"
                                noWrap
                                onClick={() => {
                                    if (!user) {
                                        setOpen(true);
                                    } else {
                                        setUser(null);
                                    }
                                }}
                                sx={{
                                    mr: 2,
                                    fontFamily: 'monospace',
                                    fontWeight: 700,
                                    color: 'inherit',
                                    textDecoration: 'none',
                                    cursor: 'pointer',
                                }}
                            >
                                {user ? 'Log out' : 'Log in'}
                            </Typography>
                        </Box>
                    </Toolbar>
                </Container>
            </AppBar>
            <LoginForm isOpen={isOpen} onClose={handleClose} />
        </>
    );
}
