import React from 'react';

import {AppRouterCacheProvider} from '@mui/material-nextjs/v15-appRouter';
import {ThemeProvider} from '@mui/material/styles';
import CssBaseline from '@mui/material/CssBaseline';
import theme from '@/theme';
import {Header} from "@/components/Header";
import {Providers} from "@/providers";

import './main.css';

export default function RootLayout(props) {
    return (
        <html lang="en">
            <body>
                <AppRouterCacheProvider options={{enableCssLayer: true}}>
                    <Providers>
                        <ThemeProvider theme={theme}>
                            <CssBaseline/>
                            <Header/>
                                <main>{props.children}</main>
                        </ThemeProvider>
                    </Providers>
                </AppRouterCacheProvider>
            </body>
        </html>
    );
}